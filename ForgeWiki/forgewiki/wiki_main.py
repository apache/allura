#-*- python -*-
import difflib
import logging
from pprint import pformat
from mimetypes import guess_type

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
from pyforge.lib.helpers import push_config, tag_artifact, DateTimeConverter, diff_text
from pyforge.lib.search import search
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole, User, TagEvent, UserTags, ArtifactReference, Tag, Feed

# Local imports
from forgewiki import model
from forgewiki import version

log = logging.getLogger(__name__)

# Will not be needed after _dispatch is fixed in tg 2.1
from pyforge.lib.dispatch import _dispatch

class ForgeWikiApp(Application):
    '''This is the Wiki app for PyForge'''
    __version__ = version.__version__
    permissions = [ 'configure', 'read', 'create', 'edit', 'delete', 'comment', 'edit_page_permissions' ]
    config_options = Application.config_options + [
        ConfigOption('project_name', str, 'pname'),
        ConfigOption('message', str, 'Custom message goes here'),
        ]

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()

    def has_access(self, user, topic):
        return user != User.anonymous()

    @audit('Wiki.#')
    def auditor(self, routing_key, data):
        '''Attach a comment to the named page'''
        log.info('Auditing data from %s (%s)',
                 routing_key, self.config.options.mount_point)
        log.info('Headers are: %s', data['headers'])
        try:
            elements = routing_key.split('.')
            count = len(elements)
            log.info('Audit applies to page ' + elements[1])
            p = model.Page.upsert(elements[1])
        except:
            log.info('Audit applies to page Root.')
            p = model.Page.upsert('Root')
        # Find ancestor comment
        parent = model.Comment.query.get(message_id=data['headers'].get('In-Reply-To'))
        if parent is None: parent = p
        comment = parent.reply()
        if 'Message-ID' in data['headers']:
            comment.message_id=data['headers']['Message-ID']
        comment.text = '*%s*\n\n%s' % (
            data['headers'].get('Subject'),
            data['payload'])
        log.info('Set subject to %s', data['headers'].get('Subject'))

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
    def sitemap(self):
        menu_id = 'ForgeWiki (%s)' % self.config.options.mount_point
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
        links = [SitemapEntry('Home',c.app.url)]
        if page:
            links.append(SitemapEntry('Edit this page','edit'))
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
            links.append(SitemapEntry('View History','history'))
        links = links + [
		    SitemapEntry('Browse Pages',c.app.url+'browse_pages/'),
		    SitemapEntry('Browse Tags',c.app.url+'browse_tags/'),
		    SitemapEntry('Help'),
		    SitemapEntry('Wiki Help',c.app.url+'wiki_help/'),
		    SitemapEntry('Markdown Syntax',c.app.url+'markdown_syntax/')
        ]
        return links

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgewiki', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'

        self.config.options['project_name'] = project._id
        self.uninstall(project)
        # Give the installing user all the permissions
        pr = c.user.project_role()
        for perm in self.permissions:
              self.config.acl[perm] = [ pr._id ]
        self.config.acl['read'].append(
            ProjectRole.query.get(name='*anonymous')._id)
        self.config.acl['comment'].append(
            ProjectRole.query.get(name='*authenticated')._id)
        p = model.Page.upsert('Root')    
        p.viewable_by = ['all']
        p.text = 'This is the root page.'
        p.commit()

    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        Application.uninstall(self, project)
        model.Attachment.query.remove({'metadata.app_config_id':c.app.config._id})
        mapper(model.Page).remove(dict(project_id=c.project._id))
        mapper(model.Comment).remove(dict(project_id=c.project._id))

class RootController(object):

    def __init__(self):
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)

    @expose('forgewiki.templates.index')
    def index(self):
        redirect('Root/')
        return dict(message=c.app.config.options['message'])

    #Instantiate a Page object, and continue dispatch there
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
        'list of all tags in the wiki'
        tags = Tag.query.find({'artifact_ref.mount_point':c.app.config.options.mount_point,
                               'artifact_ref.project_id':c.app.config.project_id}).all()
        page_tags = {}
        for tag in tags:
            artifact = ArtifactReference(tag.artifact_ref).to_artifact()
            if isinstance(artifact, model.Page):
                if tag.tag not in page_tags:
                    page_tags[tag.tag] = []
                page_tags[tag.tag].append(artifact)
        return dict(tags=page_tags)

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
    def feed(self, since, until, offset, limit):
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
        self.comments = CommentController(self.page)
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
        return dict(page=page,
                    cur=cur, prev=prev, next=next)

    @without_trailing_slash
    @expose('forgewiki.templates.page_edit')
    def edit(self):
        if self.page.version == 1:
            require(has_artifact_access('create', self.page))
        else:
            require(has_artifact_access('edit', self.page))
            if 'all' not in self.page.viewable_by and str(c.user._id) not in self.page.viewable_by:
                raise exc.HTTPForbidden(detail="You may not view this page.")
        user_tags = UserTags.upsert(c.user, self.page.dump_ref())
        return dict(page=self.page, user_tags=user_tags)

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
    def feed(self, since, until, offset, limit):
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
    def update(self, text, tags, tags_old, viewable_by):
        require(has_artifact_access('edit', self.page))
        if tags: tags = tags.split(',')
        else: tags = []
        self.page.text = text
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
        with model.Attachment.create(
            content_type=content_type,
            filename=filename,
            page_id=self.page._id,
            app_config_id=c.app.config._id) as fp:
            while True:
                s = file_info.file.read()
                if not s: break
                fp.write(s)
        redirect('.')

class AttachmentsController(object):

    def __init__(self, page):
        self.page = page

    def _lookup(self, filename, *args):
        return AttachmentController(filename), args

class AttachmentController(object):

    def _check_security(self):
        require(has_artifact_access('read', self.page))

    def __init__(self, filename):
        self.filename = filename
        self.attachment = model.Attachment.query.get(filename=filename)
        self.page = self.attachment.page

    @expose()
    def index(self, delete=False, embed=False):
        if request.method == 'POST':
            require(has_artifact_access('edit', self.page))
            if delete: self.attachment.delete()
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

class CommentController(object):

    def __init__(self, page, comment_id=None):
        self.page = page
        self.comment_id = comment_id
        self.comment = model.Comment.query.get(slug=self.comment_id)

    @expose()
    def reply(self, text):
        require(has_artifact_access('comment', self.page))
        if self.comment_id:
            c = self.comment.reply(text)
        else:
            c = self.page.reply(text)
        email = ''
        for addr in c.author().email_addresses:
            email = email + ', ' + addr
        data = {
#            'destinations':email,
            'text':text,
            'from':str(self.page),
            'subject':str('reply to '+c._id),
            'message_id':c._id}
        g.publish('audit', 'forgewiki.reply', data, 
            serializer='yaml')
        redirect(request.referer)

    @expose()
    def delete(self):
        require(lambda:c.user._id == self.comment.author()._id)
        self.comment.delete()
        redirect(request.referer)

    def _lookup(self, next, *remainder):
        if self.comment_id:
            return CommentController(
                self.page,
                self.comment_id + '/' + next), remainder
        else:
            return CommentController(
                self.page, next), remainder

MARKDOWN_EXAMPLE='''
# First-level heading

Some *emphasized* and **strong** text

#### Fourth-level heading

'''
