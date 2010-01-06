#-*- python -*-
import difflib
import logging
from pprint import pformat

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect
from pylons import g, c, request
from formencode import validators
from pymongo.bson import ObjectId

from ming.orm.base import mapper

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry
from pyforge.lib.helpers import push_config
from pyforge.lib.search import search
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole

# Local imports
from forgewiki import model
from forgewiki import version

log = logging.getLogger(__name__)

# Will not be needed after _dispatch is fixed in tg 2.1
from pyforge.lib.dispatch import _dispatch

class ForgeWikiApp(Application):
    '''This is the Wiki app for PyForge'''
    __version__ = version.__version__
    permissions = [ 'configure', 'read', 'create', 'edit', 'delete', 'comment' ]
    config_options = Application.config_options + [
        ConfigOption('project_name', str, 'pname'),
        ConfigOption('message', str, 'Custom message goes here'),
        ]

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()

    @audit('Wiki.#')
    def auditor(self, routing_key, data):
        log.info('JTB13 Auditing data from %s (%s)',
                 routing_key, self.config.options.mount_point)
        try:
            elements = routing_key.split('.')
            count = len(elements)
        except:
            log.info('Audit applies to page Root.')
            p = model.Page.upsert('Root')
        else:
            log.info('JTB13 Audit applies to page ' + elements[1])
            p = model.Page.upsert(elements[1])
            try:
#                p.text = 'This is the JTB13 test page:' + data.body
#                p.text = str(data)
                p.text = str(data['body'])
                p.commit()
#                c = p.reply()
#                c.text = 'This is a test comment.'
#                c.m.save()
            except:
                log.info('JTB13 failed to configure wiki')
            else:
                log.info('JTB13 configured wiki')

    @react('Wiki.#')
    def reactor(self, routing_key, data):
        log.info('Reacting to data from %s (%s)',
                 routing_key, self.config.options.mount_point)

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
        return [
            SitemapEntry(p.title, p.url())
            for p in model.Page.query.find(dict(
                    app_config_id=self.config._id)) ]

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
        p.text = 'This is the root page.'
        p.commit()

    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        mapper(model.Page).remove(dict(project_id=c.project._id))
        mapper(model.Comment).remove(dict(project_id=c.project._id))

class RootController(object):

    @expose('forgewiki.templates.index')
    def index(self):
        redirect('Root/')
        return dict(message=c.app.config.options['message'])

    #Will not be needed after _dispatch is fixed in tg 2.1
    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)

    #Instantiate a Page object, and continue dispatch there
    def _lookup(self, pname, *remainder):
        return PageController(pname), remainder

    @expose()
    def new_page(self, title):
        redirect(title + '/')

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

class PageController(object):

    def __init__(self, title):
        self.title = title
        self.page = model.Page.upsert(title)
        self.comments = CommentController(self.page)

    def get_version(self, version):
        if not version: return self.page
        try:
            return model.Page.upsert(self.title, version=int(version))
        except ValueError:
            return None

    @expose('forgewiki.templates.page_view')
    @validate(dict(version=validators.Int(if_empty=None)))
    def index(self, version=None):
        require(has_artifact_access('read', self.page))
        page = self.get_version(version)
        if page is None:
            if version: redirect('.?version=%d' % (version-1))
            else: redirect('.')
        cur = page.version
        if cur > 1: prev = cur-1
        else: prev = None
        next = cur+1
        return dict(page=page,
                    cur=cur, prev=prev, next=next)

    @expose('forgewiki.templates.page_edit')
    def edit(self):
        if self.page.version == 1:
            require(has_artifact_access('create', self.page))
        else:
            require(has_artifact_access('edit', self.page))
        return dict(page=self.page,
                    example=MARKDOWN_EXAMPLE)

    @expose('forgewiki.templates.page_history')
    def history(self):
        require(has_artifact_access('read', self.page))
        pages = self.page.history()
        return dict(title=self.title, pages=pages)

    @expose('forgewiki.templates.page_diff')
    def diff(self, v1, v2):
        require(has_artifact_access('read', self.page))
        p1 = self.get_version(int(v1))
        p2 = self.get_version(int(v2))
        t1 = p1.text
        t2 = p2.text
        differ = difflib.SequenceMatcher(None, p1.text, p2.text)
        result = []
        for tag, i1, i2, j1, j2 in differ.get_opcodes():
            if tag in ('delete', 'replace'):
                result += [ '<del>', t1[i1:i2], '</del>' ]
            if tag in ('insert', 'replace'):
                result += [ '<ins>', t2[j1:j2], '</ins>' ]
            if tag == 'equal':
                result += t1[i1:i2]
        result = ''.join(result).replace('\n', '<br/>\n')
        return dict(p1=p1, p2=p2, edits=result)

    @expose(content_type='text/plain')
    def raw(self):
        require(has_artifact_access('read', self.page))
        return pformat(self.page)

    @expose()
    def revert(self, version):
        require(has_artifact_access('edit', self.page))
        orig = self.get_version(version)
        self.page.text = orig.text
        self.page.commit()
        redirect('.')

    @expose()
    def update(self, text):
        require(has_artifact_access('edit', self.page))
        self.page.text = text
        self.page.commit()
        redirect('.')

class CommentController(object):

    def __init__(self, page, comment_id=None):
        self.page = page
        self.comment_id = comment_id
        self.comment = model.Comment.query.get(_id=self.comment_id)

    @expose()
    def reply(self, text):
        require(has_artifact_access('comment', self.page))
        if self.comment_id:
            c = self.comment.reply()
            c.text = text
        else:
            c = self.page.reply()
            c.text = text
        redirect(request.referer)

    @expose()
    def delete(self):
        require(lambda:c.user._id == self.comment.author()._id)
        self.comment.delete()
        redirect(request.referer)

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)

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
