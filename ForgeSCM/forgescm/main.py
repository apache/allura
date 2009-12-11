#-*- python -*-
import os
import logging

# Non-stdlib imports
import pkg_resources
from pylons import g, c
from ming import schema


# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry
from pyforge.lib.helpers import push_config, mixin_reactors
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole

# Local imports
from . import model
from . import version
from .wsgi import WSGIHook
from .reactors import hg_react
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
        return model.Repository.m.get(app_config_id=self.config._id)

    @property
    def sitemap(self):
        menu_id = 'Repository (%s)' % self.config.options.mount_point  
        with push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def sidebar_menu(self):
        result = [
            SitemapEntry('Home', '.'),      
            SitemapEntry('Search', 'search'),
            ]
        if self.config.options.type == 'hg':
            repo = self.repo
            result += [
                SitemapEntry('HgWeb', repo.native_url()),
                SitemapEntry('Files', repo.native_url() + '/file') ]
        return result

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
                status='Pending',
                type=self.config.options['type']))
        repo.m.insert()

    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        model.Repository.m.remove(dict(app_config_id=self.config._id))

mixin_reactors(ForgeSCMApp, hg_react)

