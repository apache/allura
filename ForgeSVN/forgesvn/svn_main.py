#-*- python -*-
import logging

# Non-stdlib imports
import pkg_resources
from pylons import g

from ming.utils import LazyProperty
from ming.orm.ormsession import ThreadLocalORMSession

# Pyforge-specific imports
from allura.controllers.repository import RepoRootController
from allura.lib.repository import RepositoryApp

# Local imports
from . import model as SM
from . import version
from .controllers import BranchBrowser

log = logging.getLogger(__name__)

class ForgeSVNApp(RepositoryApp):
    '''This is the SVN app for PyForge'''
    __version__ = version.__version__
    tool_label='SVN'
    ordinal=4
    forkable=False
    default_branch_name=''

    def __init__(self, project, config):
        super(ForgeSVNApp, self).__init__(project, config)
        self.root = BranchBrowser()
        default_root = RepoRootController()
        self.root.refresh = default_root.refresh
        self.root.feed = default_root.feed

    @LazyProperty
    def repo(self):
        return SM.Repository.query.get(app_config_id=self.config._id)

    def install(self, project):
        '''Create repo object for this tool'''
        super(ForgeSVNApp, self).install(project)
        repo = SM.Repository(
            name=self.config.options.mount_point,
            tool='svn',
            status='initing')
        ThreadLocalORMSession.flush_all()
        g.publish('audit', 'repo.init',
                  dict(repo_name=repo.name, repo_path=repo.fs_path))
