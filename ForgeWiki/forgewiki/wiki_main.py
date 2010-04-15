#-*- python -*-
import difflib
import logging
from pprint import pformat
from mimetypes import guess_type
import Image

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import g, c, request
from formencode import validators
from pymongo import bson
from webob import exc

from ming.orm.base import mapper
from pymongo.bson import ObjectId

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry
from pyforge.lib.helpers import push_config, tag_artifact, DateTimeConverter, diff_text, square_image
from pyforge.lib.search import search
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole, User, TagEvent, UserTags, ArtifactReference, Tag, Feed
from pyforge.model import Discussion, Thread, Post, Attachment, Subscriptions
from pyforge.controllers import AppDiscussionController
from pyforge.lib import widgets as w
from pyforge.lib.widgets import form_fields as ffw
from pyforge.lib.widgets.subscriptions import SubscribeForm

# Local imports
from forgewiki import model
from forgewiki import version

log = logging.getLogger(__name__)

class W:
    thread=w.Thread(
        offset=None, limit=None, page_size=None, total=None,
        style='linear')
    markdown_editor = ffw.MarkdownEdit()
    user_tag_edit = ffw.UserTagEdit()
    label_edit = ffw.LabelEdit()
    attachment_list = ffw.AttachmentList()
    subscribe_form = SubscribeForm()
    page_subscribe_form = SubscribeForm(thing='page')


class ForgeWikiApp(Application):
    '''This is the Wiki app for PyForge'''
    __version__ = version.__version__
    permissions = [ 'configure', 'read', 'create', 'edit', 'delete', 'edit_page_permissions',
                    'unmoderated_post', 'post', 'moderate', 'admin']

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()

    def has_access(self, user, topic):
        return has_artifact_access('post', user=user)

    @audit('Wiki.msg.#')
    def message_auditor(self, routing_key, data):
        log.info('Auditing data from %s (%s)',
                 routing_key, self.config.options.mount_point)
        log.info('Headers are: %s', data['headers'])
        try:
            title = routing_key.split('.')[-1]
            p = model.Page.upsert(title)
        except:
            log.info('Audit applies to page Root.')
            p = model.Page.upsert('Root')
        super(ForgeWikiApp, self).message_auditor(routing_key, data, p)

    @react('Wiki.#')
    def reactor(self, routing_key, data):
        log.info('Reacting to data from %s (%s)',
                 routing_key, self.config.options.mount_point)

    @audit('forgewiki.reply')
    def audit_reply(self, routing_key, data):
        log.info('Auditing reply from %s (%s)',
                 routing_key, self.config.options.mount_point)
        # 'data' should be a dictionary which includes:
        # destinations, text, from, subject, message_id
        data['destinations'] = 'devnull@localhost'
        g.publish('audit', 'forgemail.send_email',
            data, serializer='yaml')

    @property
    def root_page_name(self):
        return self.config.options.mount_point.title() + 'Home'

    @property
    def sitemap(self):
        menu_id = self.config.options.mount_point.title()
        with push_config(c, app=self):
            pages = [
                SitemapEntry(p.title, p.url())
                for p in model.Page.query.find(dict(
                        app_config_id=self.config._id)) ]
            return [
                SitemapEntry(menu_id, '.')[SitemapEntry('Pages')[pages]] ]

    def sidebar_menu(self):
        related_pages = []
        related_urls = []
        page = request.path_info.split(self.url)[-1].split('/')[-2]
        page = model.Page.query.find(dict(app_config_id=self.config._id,title=page)).first()
        links = [SitemapEntry('Home',c.app.url, ui_icon='home'),
                 SitemapEntry('Discuss', c.app.url + '_discuss/', ui_icon='comment') ]
        if page:
            links.append(SitemapEntry('Edit this page','edit', ui_icon='check'))
            for aref in page.references+page.backreferences.values():
                artifact = ArtifactReference(aref).to_artifact()
                if isinstance(artifact, model.Page) and artifact.url() not in related_urls:
                    related_urls.append(artifact.url())
                    related_pages.append(SitemapEntry(artifact.title, artifact.url(), className='nav_child'))
        if len(related_pages):
            links.append(SitemapEntry('Related Pages'))
            links = links + related_pages
        links.append(SitemapEntry('Wiki Nav'))
        if page:
            links.append(SitemapEntry('View History','history', className='nav_child'))
        links = links + [
		    SitemapEntry('Browse Pages',c.app.url+'browse_pages/', className='nav_child'),
		    SitemapEntry('Browse Tags',c.app.url+'browse_tags/', className='nav_child'),
		    SitemapEntry('Help'),
		    SitemapEntry('Wiki Help',c.app.url+'wiki_help/', className='nav_child'),
		    SitemapEntry('Markdown Syntax',c.app.url+'markdown_syntax/', className='nav_child')
        ]
        return links

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgewiki', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project._id
        self.uninstall(project)
        super(ForgeWikiApp, self).install(project)
        # Setup permissions
        role_developer = ProjectRole.query.get(name='Developer')._id
        role_auth = ProjectRole.query.get(name='*authenticated')._id
        self.config.acl.update(
            configure=c.project.acl['plugin'],
            read=c.project.acl['read'],
            create=[role_developer],
            edit=[role_developer],
            delete=[role_developer],
            edit_page_permissions=c.project.acl['plugin'],
            unmoderated_post=[role_developer],
            post=[role_auth],
            moderate=[role_developer],
            admin=c.project.acl['plugin'])
        p = model.Page.upsert(self.root_page_name)
        p.viewable_by = ['all']
        url = c.app.url + 'markdown_syntax' + '/'
        p.text = """Welcome to your wiki!

This is the default page, edit it as you see fit. To add a page simply reference it with camel case, e.g.: SamplePage.

The wiki uses [Markdown](%s) syntax.
""" % url
        p.commit()


    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        model.Attachment.query.remove({'metadata.app_config_id':c.app.config._id})
        model.Page.query.remove(dict(app_config_id=c.app.config._id))
        Application.uninstall(self, project)

class RootController(object):

    def __init__(self):
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)
        self._discuss = AppDiscussionController()

    @expose('forgewiki.templates.index')
    def index(self):
        redirect(c.app.root_page_name+'/')
        return dict(message=c.app.config.options['message'])

    #Instantiate a Page object, and continue dispatch there
    @expose()
    def _lookup(self, pname, *remainder):
        return PageController(pname), remainder

    @expose()
    def new_page(self, title):
        redirect(title + '/')

    @with_trailing_slash
    @expose('forgewiki.templates.search')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None):
        'local wiki search'
        results = []
        count=0
        if not q:
            q = ''
        else:
            search_query = '''%s
            AND is_history_b:%s
            AND project_id_s:%s
            AND mount_point_s:%s''' % (
                q, history, c.project._id, c.app.config.options.mount_point)
            results = search(search_query)
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

    @with_trailing_slash
    @expose('forgewiki.templates.browse')
    @validate(dict(sort=validators.UnicodeString(if_empty='alpha')))
    def browse_pages(self, sort='alpha'):
        'list of all pages in the wiki'
        pages = []
        uv_pages = []
        q = model.Page.query.find(dict(app_config_id=c.app.config._id))
        if sort == 'alpha':
            q = q.sort('title')
        for page in q:
            recent_edit = page.history().first()
            p = dict(title=page.title)
            if recent_edit:
                p['updated'] = recent_edit.timestamp
                p['user_label'] = recent_edit.author.display_name
                p['user_name'] = recent_edit.author.username
                pages.append(p)
            else:
                if sort == 'recent':
                    uv_pages.append(p)
                else:
                    pages.append(p)
        if sort == 'recent':
            pages.sort(reverse=True, key=lambda x:(x['updated']))
            pages = pages + uv_pages
        return dict(pages=pages)

    @with_trailing_slash
    @expose('forgewiki.templates.browse_tags')
    @validate(dict(sort=validators.UnicodeString(if_empty='alpha')))
    def browse_tags(self, sort='alpha'):
        'list of all labels in the wiki'
        page_tags = {}
        # tags = Tag.query.find({'artifact_ref.mount_point':c.app.config.options.mount_point,
        #                        'artifact_ref.project_id':c.app.config.project_id}).all()
        # for tag in tags:
        #     artifact = ArtifactReference(tag.artifact_ref).to_artifact()
        #     if isinstance(artifact, model.Page):
        #         if tag.tag not in page_tags:
        #             page_tags[tag.tag] = []
        #         page_tags[tag.tag].append(artifact)
        q = model.Page.query.find(dict(app_config_id=c.app.config._id))
        for page in q:
            if page.labels:
                for label in page.labels:
                    if label not in page_tags:
                        page_tags[label] = []
                    page_tags[label].append(page)
        return dict(labels=page_tags)

    @with_trailing_slash
    @expose('forgewiki.templates.markdown_syntax')
    def markdown_syntax(self):
        'Display a page about how to use markdown.'
        return dict(example=MARKDOWN_EXAMPLE)

    @with_trailing_slash
    @expose('forgewiki.templates.wiki_help')
    def wiki_help(self):
        'Display a help page about using the wiki.'
        return dict()

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=DateTimeConverter(if_empty=None),
            until=DateTimeConverter(if_empty=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, offset=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent changes to %s' % c.app.config.options.mount_point
        feed = Feed.feed(
            {'artifact_reference.mount_point':c.app.config.options.mount_point,
             'artifact_reference.project_id':c.project._id},
            feed_type,
            title,
            c.app.url,
            title,
            since, until, offset, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

class PageController(object):

    def __init__(self, title):
        exists = model.Page.query.find(dict(app_config_id=c.app.config._id, title=title)).first()
        self.title = title
        self.page = model.Page.upsert(title)
        self.attachment = AttachmentsController(self.page)
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)
        if not exists:
            self.page.viewable_by = ['all']
            redirect(c.app.url+title+'/edit')

    def get_version(self, version):
        if not version: return self.page
        try:
            return model.Page.upsert(self.title, version=int(version))
        except ValueError:
            return None

    @with_trailing_slash
    @expose('forgewiki.templates.page_view')
    @validate(dict(version=validators.Int(if_empty=None)))
    def index(self, version=None):
        require(has_artifact_access('read', self.page))
        c.thread = W.thread
        c.attachment_list = W.attachment_list
        c.subscribe_form = W.page_subscribe_form
        page = self.get_version(version)
        if 'all' not in page.viewable_by and str(c.user._id) not in page.viewable_by:
            raise exc.HTTPForbidden(detail="You may not view this page.")
        if page is None:
            if version: redirect('.?version=%d' % (version-1))
            else: redirect('.')
        cur = page.version
        if cur > 1: prev = cur-1
        else: prev = None
        next = cur+1
        return dict(
            page=page,
            cur=cur, prev=prev, next=next,
            subscribed=Subscriptions.upsert().subscribed(artifact=self.page))

    @without_trailing_slash
    @expose('forgewiki.templates.page_edit')
    def edit(self):
        if self.page.version == 1:
            require(has_artifact_access('create', self.page))
        else:
            require(has_artifact_access('edit', self.page))
            if 'all' not in self.page.viewable_by and str(c.user._id) not in self.page.viewable_by:
                raise exc.HTTPForbidden(detail="You may not view this page.")
        c.markdown_editor = W.markdown_editor
        c.user_select = ffw.ProjectUserSelect()
        c.attachment_list = W.attachment_list
        c.label_edit = W.label_edit
        return dict(page=self.page)

    @without_trailing_slash
    @expose('forgewiki.templates.page_history')
    def history(self):
        require(has_artifact_access('read', self.page))
        pages = self.page.history()
        return dict(title=self.title, pages=pages)

    @without_trailing_slash
    @expose('forgewiki.templates.page_diff')
    def diff(self, v1, v2):
        require(has_artifact_access('read', self.page))
        p1 = self.get_version(int(v1))
        p2 = self.get_version(int(v2))
        result = diff_text(p1.text, p2.text)
        return dict(p1=p1, p2=p2, edits=result)

    @without_trailing_slash
    @expose(content_type='text/plain')
    def raw(self):
        require(has_artifact_access('read', self.page))
        return pformat(self.page)

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=DateTimeConverter(if_empty=None),
            until=DateTimeConverter(if_empty=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, offset=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        feed = Feed.feed(
            {'artifact_reference':self.page.dump_ref()},
            feed_type,
            'Recent changes to %s' % self.page.title,
            self.page.url(),
            'Recent changes to %s' % self.page.title,
            since, until, offset, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

    @without_trailing_slash
    @expose()
    def revert(self, version):
        require(has_artifact_access('edit', self.page))
        orig = self.get_version(version)
        if orig:
            self.page.text = orig.text
        self.page.commit()
        redirect('.')

    @without_trailing_slash
    @expose()
    def update(self, text=None, tags=None, tags_old=None, labels=None, labels_old=None, viewable_by=None):
        require(has_artifact_access('edit', self.page))
        if tags: tags = tags.split(',')
        else: tags = []
        self.page.text = text
        self.page.labels = labels.split(',')
        self.page.commit()
        tag_artifact(self.page, c.user, tags)
        self.page.viewable_by = isinstance(viewable_by, list) and viewable_by or viewable_by.split(',')
        redirect('.')

    @without_trailing_slash
    @expose()
    def attach(self, file_info=None):
        require(has_artifact_access('edit', self.page))
        filename = file_info.filename
        content_type = guess_type(filename)
        if content_type: content_type = content_type[0]
        else: content_type = 'application/octet-stream'
        if h.supported_by_PIL(file_info.type):
            image = Image.open(file_info.file)
            format = image.format
            with model.Attachment.create(
                content_type=content_type,
                filename=filename,
                page_id=self.page._id,
                type="attachment",
                app_config_id=c.app.config._id) as fp:
                fp_name = fp.name
                image.save(fp, format)
            image = square_image(image)
            image.thumbnail((150, 150), Image.ANTIALIAS)
            with model.Attachment.create(
                content_type=content_type,
                filename=fp_name,
                page_id=self.page._id,
                type="thumbnail",
                app_config_id=c.app.config._id) as fp:
                image.save(fp, format)
        else:
            with model.Attachment.create(
                content_type=content_type,
                filename=filename,
                page_id=self.page._id,
                type="attachment",
                app_config_id=c.app.config._id) as fp:
                while True:
                    s = file_info.file.read()
                    if not s: break
                    fp.write(s)
        redirect('.')

    @expose()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None):
        require(has_artifact_access('read'))
        if subscribe:
            Subscriptions.upsert().subscribe('direct', artifact=self.page)
        elif unsubscribe:
            Subscriptions.upsert().unsubscribe(artifact=self.page)
        redirect(request.referer)

class AttachmentsController(object):

    def __init__(self, page):
        self.page = page

    @expose()
    def _lookup(self, filename, *args):
        return AttachmentController(filename), args

class AttachmentController(object):

    def _check_security(self):
        require(has_artifact_access('read', self.page))

    def __init__(self, filename):
        self.filename = filename
        self.attachment = model.Attachment.query.get(filename=filename)
        self.thumbnail = model.Attachment.by_metadata(filename=filename).first()
        self.page = self.attachment.page

    @expose()
    def index(self, delete=False, embed=False):
        if request.method == 'POST':
            require(has_artifact_access('edit', self.page))
            if delete:
                self.attachment.delete()
                self.thumbnail.delete()
            redirect(request.referer)
        with self.attachment.open() as fp:
            filename = fp.metadata['filename']
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type
            if not embed:
                response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return self.filename

    @expose()
    def thumb(self, embed=False):
        with self.thumbnail.open() as fp:
            filename = fp.metadata['filename']
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type
            if not embed:
                response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return self.filename

MARKDOWN_EXAMPLE='''
# First-level heading

Some *emphasized* and **strong** text

#### Fourth-level heading

'''
