#-*- python -*-
import logging

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect
from pylons import g, c, request
from formencode import validators
from pymongo.bson import ObjectId

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

class ForgeWikiApp(Application):
    __version__ = version.__version__
    permissions = ['configure', 'read', 'write', 'comment']
    config_options = Application.config_options + [
        ConfigOption('some_str_config_option', str, 'some_str_config_option'),
        ConfigOption('some_int_config_option', int, 42),
        ]

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()

    @audit('Wiki.#')
    def auditor(self, routing_key, data):
        log.info('Auditing data from %s (%s)',
                 routing_key, self.config.options.mount_point)

    @react('Wiki.#')
    def reactor(self, routing_key, data):
        log.info('Reacting to data from %s (%s)',
                 routing_key, self.config.options.mount_point)

    @property
    def sitemap(self):
        menu_id = 'ForgeWiki (%s)' % self.config.options.mount_point  
        with push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def sidebar_menu(self):
        return [
            SitemapEntry('Home', '.'),      
            SitemapEntry('Search', 'search'),      
            ]

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgewiki', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'

        self.uninstall(project)
        # Give the installing user all the permissions
        pr = c.user.project_role()
        for perm in self.permissions:
              self.config.acl[perm] = [ pr._id ]
        self.config.acl['read'].append(
            ProjectRole.m.get(name='*anonymous')._id)      
        self.config.acl['comment'].append(
            ProjectRole.m.get(name='*authenticated')._id)
        self.config.m.save()
        art = model.MyArtifact.make(dict(
                text='This is a sample artifact'))
        art.commit()

    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        pass

class RootController(object):

    @expose('forgewiki.templates.index')
    def index(self):
        return dict()
                  
    @expose('forgewiki.templates.search')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None):
        'local plugin search'
        results = []
        count=0
        if not q:
            q = ''
        else:
            search_query = '''%s
            AND is_history_b:%s
            AND mount_point_s:%s''' % (
                q, history, c.app.config.options.mount_point)
            results = search(search_query)
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

    def _lookup(self, id, *remainder):
        return ArtifactController(id), remainder

class ArtifactController(object):

    def __init__(self, id):
        self.artifact = model.MyArtifact.m.get(_id=ObjectId.url_decode(id))
        self.comments = CommentController(self.artifact)

    @expose('forgewiki.templates.artifact')
    @validate(dict(version=validators.Int()))
    def index(self, version=None):
        require(has_artifact_access('read', self.artifact))
        artifact = self.get_version(version)
        if artifact is None:
            if version:
                redirect('.?version=%d' % (version-1))
            elif version <= 0:
                redirect('.')
            else:
                redirect('..')
        cur = artifact.version
        if cur > 0: prev = cur-1
        else: prev = None
        next = cur+1
        return dict(artifact=artifact,
                    cur=cur, prev=prev, next=next)

    def get_version(self, version):
        if not version: return self.artifact
        ss = model.MyArtifactHistory.m.get(artifact_id=self.artifact._id,
                                           version=version)
        if ss is None: return None
        result = deepcopy(self.artifact)
        return result.update(ss.data)
    
class CommentController(object):

    def __init__(self, artifact, comment_id=None):
        self.artifact = artifact
        self.comment_id = comment_id
        self.comment = model.MyArtifactComment.m.get(_id=self.comment_id)

    @expose()
    def reply(self, text):
        require(has_artifact_access('comment', self.artifact))
        if self.comment_id:
            c = self.comment.reply()
            c.text = text
        else:
            c = self.artifact.reply()
            c.text = text
        c.m.save()
        redirect(request.referer)

    @expose()
    def delete(self):
        require(lambda:c.user._id == self.comment.author()._id)
        self.comment.m.delete()
        redirect(request.referer)

    def _lookup(self, next, *remainder):
        if self.comment_id:
            return CommentController(
                self.artifact,
                self.comment_id + '/' + next), remainder
        else:
            return CommentController(
                self.artifact, next), remainder

    
    
