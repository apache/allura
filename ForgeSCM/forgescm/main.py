#-*- python -*-
import os
import shutil
import logging
from cStringIO import StringIO
from pprint import pformat

# Non-stdlib imports
import pkg_resources
import uvc.main, uvc.hg, uvc.util
from tg import expose, validate, redirect
from pylons import g, c, request
from formencode import validators
from pymongo.bson import ObjectId
from ming import schema


# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry
from pyforge.lib.helpers import push_config
from pyforge.lib.search import search
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole

# Local imports
from forgescm import model
from forgescm import version
from forgescm.wsgi import WSGIHook

log = logging.getLogger(__name__)

class ForgeSCMApp(Application):
    __version__ = version.__version__
    permissions = ['configure', 'read' ]
    config_options = Application.config_options + [
        ConfigOption('type', schema.OneOf('git', 'hg', 'svn'), 'hg'),
        ]
    wsgi=WSGIHook()

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()

    @property
    def repo(self):
        return model.Repository.m.get()

    @audit('scm.hg.init')
    def scm_hg_init(self, routing_key, data):
        log.info('Got hg init command: %s', pformat(data))
        repo_dir = pkg_resources.resource_filename(
            'forgescm',
            os.path.join('data', c.project._id, c.app.config.options.mount_point))
        log.info('Initializing repository at %s', repo_dir)
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir)
        os.makedirs(repo_dir)
        ctx = uvc.main.Context(repo_dir)
        command = uvc.hg.init(ctx, [])
        output = StringIO()
        uvc.util.run_in_directory(
            repo_dir,
            command.get_command_line(),
            output=output)
        repo = self.repo
        repo.status = 'Ready'
        repo.m.save()

    @property
    def sitemap(self):
        menu_id = 'Repository (%s)' % self.config.options.mount_point  
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
         return pkg_resources.resource_filename('forgescm', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'

        self.uninstall(project)
        # Give the installing user all the permissions
        pr = c.user.project_role()
        for perm in self.permissions:
              self.config.acl[perm] = [ pr._id ]
        self.config.acl['read'].append(
            ProjectRole.m.get(name='*anonymous')._id)      
        self.config.m.save()
        # Create a repository
        repo = model.Repository.make(dict(
                description='This is the repository object',
                status='Pending'))
        repo.m.insert()
        rk = 'scm.%s.init' % self.config.options.type
        g.publish('audit', rk, {})

    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        pass

class RootController(object):

    @expose('forgescm.templates.index')
    def index(self):
        return dict()
                  
    @expose('forgescm.templates.search')
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

    @expose('forgescm.templates.artifact')
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
        self.comment.text = '[Text deleted by commenter]'
        self.comment.m.save()
        redirect(request.referer)

    def _lookup(self, next, *remainder):
        if self.comment_id:
            return CommentController(
                self.artifact,
                self.comment_id + '/' + next), remainder
        else:
            return CommentController(
                self.artifact, next), remainder

    
    
