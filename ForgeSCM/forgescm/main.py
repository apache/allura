#-*- python -*-
import os
import logging

# Non-stdlib imports
import pkg_resources
from pylons import g, c
import genshi
from ming import schema
from ming.orm.base import session

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry
from pyforge.lib.helpers import push_config, mixin_reactors, set_context
from pyforge.lib.security import require, has_artifact_access
from pyforge.lib.decorators import react
from pyforge.model import ProjectRole

# Local imports
from . import model
from . import version
from .wsgi import WSGIHook
from .reactors import common_react, hg_react, git_react, svn_react
from .controllers import root

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
        self.root = root.RootController()

    @property
    def repo(self):
        return model.Repository.query.get(app_config_id=self.config._id)

    @property
    def sitemap(self):
        menu_id = 'Repository (%s)' % self.config.options.mount_point  
        with push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def sidebar_menu(self):
        base = self.repo.url()
        result = [
            SitemapEntry('Home', base),      
            SitemapEntry('Search', base + 'search'),
            SitemapEntry('Init Repo', base + 'reinit'),
            ]
        repo = self.repo
        if self.config.options.type in 'hg':
            result += [
                SitemapEntry('HgWeb', repo.native_url()),
                SitemapEntry('Files', repo.native_url() + '/file') ]
        elif self.config.options.type == 'git':
            result += [
                SitemapEntry('GitWeb', repo.native_url() + '/.git') ]
        elif self.config.options.type == 'svn':
            result += [
                SitemapEntry('Browser', repo.native_url()) ]
        return result

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
            ProjectRole.query.get(name='*anonymous')._id)      
        # Create a repository
        repo_dir = pkg_resources.resource_filename(
            'forgescm',
            os.path.join('data', self.project._id, self.config.options.mount_point))
        repo = model.Repository(
            description='This is the repository object',
            status='Pending',
            type=self.config.options['type'],
            repo_dir=repo_dir)
        session(repo).flush()

    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        repo = self.repo
        if repo: repo.delete()

mixin_reactors(ForgeSCMApp, common_react)
mixin_reactors(ForgeSCMApp, hg_react)
mixin_reactors(ForgeSCMApp, git_react)
mixin_reactors(ForgeSCMApp, svn_react)

