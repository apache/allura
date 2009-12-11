#-*- python -*-
import os
import shutil
import logging
from cStringIO import StringIO
from pprint import pformat

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, flash
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
from . import model
from . import version
from .wsgi import WSGIHook
from .lib import hg

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
        return model.Repository.m.get(app_config_id=self.config._id)

    @audit('scm.hg.init')
    def scm_hg_init(self, routing_key, data):
        repo = self.repo
        cmd = hg.init()
        cmd.clean_dir()
        repo.clear_commits()
        repo.parent = None
        cmd.run()
        if cmd.sp.returncode:
            g.publish('react', 'error', dict(
                    message=cmd.output))
        else:
            log.info('Setting repo status for %s', repo)
            repo.status = 'Ready'
            repo.m.save()
                    
    @audit('scm.hg.clone')
    def scm_hg_clone(self, routing_key, data):
        repo = self.repo
        log.info('Begin cloning %s', data['url'])
        # Perform the clone
        cmd = hg.clone(data['url'], '.')
        cmd.clean_dir()
        cmd.run()
        log.info('Clone complete for %s', data['url'])
        if cmd.sp.returncode:
            errmsg = cmd.output
            g.publish('react', 'error', dict(
                    message=errmsg))
            repo.status = 'Error: %s' % errmsg
            repo.m.save()
            return
        # Update the repo status
        repo.status = 'Ready'
        repo.m.save()
        # Load the log & create refresh commit messages
        cmd = hg.scm_log('-q')
        cmd.run()
        for line in cmd.output.split('\n'):
            rev, hash = line.split(':')
            g.publish('audit', 'scm.hg.refresh_commit', dict(
                    hash=hash))
            
        # log.info('Begin log %s', data['url'])
        # cmd = hg.scm_log('-g', '-p')
        # cmd.run()
        # log.info('Log complete %s', data['url'])
        # # Clear the old set of commits
        # repo.clear_commits()
        # repo.parent = data['url']
        # parser = hg.LogParser(repo._id)
        # log.info('Begin parsing log')
        # parser.feed(StringIO(cmd.output))

    @audit('scm.hg.refresh_commit')
    def scm_hg_refresh_commit(self, routing_key, data):
        repo = self.repo
        hash = data['hash']
        log.info('Refresh commit %s', hash)
        # Load the log
        cmd = hg.scm_log('-g', '-p', '-r', hash)
        cmd.run()
        parser = hg.LogParser(repo._id)
        parser.feed(StringIO(cmd.output))

    @audit('scm.hg.fork')
    def scm_hg_fork(self, routing_key, data):
        assert False

    @audit('scm.hg.reclone')
    def scm_hg_reclone(self, routing_key, data):
        repo = self.repo
        # Perform the clone
        cmd = hg.clone(repo.parent, '.')
        cmd.clean_dir()
        cmd.run()
        if cmd.sp.returncode:
            g.publish('react', 'error', dict(
                    message=cmd.sp.stdout.read()))
            return
        # Load the log
        cmd = hg.log('-g', '-p')
        cmd.run()
        # Clear the old set of commits
        repo.clear_commits()
        parser = hg.LogParser(repo._id)
        parser.feed(StringIO(cmd.output))
        # Update the repo status
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

    @property
    def repo_dir(self):
        return pkg_resources.resource_filename(
            'forgescm',
            os.path.join('data', self.project._id, self.config.options.mount_point))

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
        model.Repository.m.remove(dict(app_config_id=self.config._id))

class RootController(object):

    def __init__(self):
        self.repo = CommitsController()

    @expose('forgescm.templates.index')
    def index(self):
        return dict(repo=c.app.repo)

    @expose('forgescm.templates.fork')
    def fork(self, project, mount_point):
        new_repo = c.app.repo.fork(project, mount_point)
        # Find projects where we can mount things
        flash('Project %s forked' % c.app.repo.url())
        redirect(new_repo.url())
                    
                  
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

    @expose()
    def reinit(self):
        repo = c.app.repo
        repo.status = 'Pending Reinit'
        repo.m.save()
        g.publish('audit', 'scm.%s.init' % c.app.config.options.type, {})
        redirect('.')
        
    @expose()
    def reclone(self):
        repo = c.app.repo
        repo.status = 'Pending Reclone'
        repo.m.save()
        g.publish('audit', 'scm.%s.reclone' % c.app.config.options.type, {})
        redirect('.')
        
    @expose()
    def clone_from(self, url=None):
        repo = c.app.repo
        repo.status = 'Pending Clone'
        repo.m.save()
        g.publish('audit', 'scm.%s.clone' % c.app.config.options.type, dict(
                url=url))
        redirect('.')

class CommitsController(object):

    def _lookup(self, id, *remainder):
        if ':' in id: id = id.split(':')[-1]
        if '%3A' in id: id = id.split('%3A')[-1]
        return CommitController(id), remainder

class CommitController(object):

    def __init__(self, id):
        self.commit = model.Commit.m.get(hash=id)

    @expose('forgescm.templates.commit_index')
    def index(self):
        return dict(value=self.commit)

    def _lookup(self, id, *remainder):
        return PatchController(id), remainder

class PatchController(object):

    def __init__(self, id):
        self.patch = model.Patch.m.get(_id=ObjectId.url_decode(id))

    @expose('forgescm.templates.patch_index')
    def index(self):
        return dict(value=self.patch)
