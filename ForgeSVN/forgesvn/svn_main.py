#-*- python -*-
import logging

# Non-stdlib imports
from ming.utils import LazyProperty
from ming.orm.ormsession import ThreadLocalORMSession

# Pyforge-specific imports
import allura.tasks.repo_tasks
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
        self.root.commit_browser = default_root.commit_browser

    @LazyProperty
    def repo(self):
        return SM.Repository.query.get(app_config_id=self.config._id)

    def install(self, project):
        '''Create repo object for this tool'''
        super(ForgeSVNApp, self).install(project)
        SM.Repository(
            name=self.config.options.mount_point,
            tool='svn',
            status='initing')
        ThreadLocalORMSession.flush_all()
        init_from_url = self.config.options.get('init_from_url')
        if init_from_url:
            allura.tasks.repo_tasks.clone.post(
                cloned_from_path=None,
                cloned_from_name=None,
                cloned_from_url=init_from_url)
        else:
            allura.tasks.repo_tasks.init.post()
