#-*- python -*-
import logging
from pylons import c

# Non-stdlib imports
from ming.utils import LazyProperty
from ming.orm.ormsession import ThreadLocalORMSession
from tg import expose
from tg.decorators import without_trailing_slash

# Pyforge-specific imports
import allura.tasks.repo_tasks
from allura.controllers.repository import RepoRootController
from allura.lib.decorators import require_post
from allura.lib.repository import RepositoryApp, RepoAdminController
from allura.app import SitemapEntry, ConfigOption

# Local imports
from . import model as SM
from . import version
from .controllers import BranchBrowser

log = logging.getLogger(__name__)

class ForgeSVNApp(RepositoryApp):
    '''This is the SVN app for PyForge'''
    __version__ = version.__version__
    config_options = RepositoryApp.config_options + [
        ConfigOption('checkout_url', str, 'trunk')
        ]
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
        self.root.commit_browser_data = default_root.commit_browser_data
        self.admin = SVNRepoAdminController(self)

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

    def admin_menu(self):
        links = super(ForgeSVNApp, self).admin_menu()
        links.append(SitemapEntry('Checkout URL', c.project.url()+'admin/'+self.config.options.mount_point+'/' + 'checkout_url', className='admin_modal'))
        return links

class SVNRepoAdminController(RepoAdminController):

    @without_trailing_slash
    @expose('jinja:forgesvn:templates/svn/checkout_url.html')
    def checkout_url(self, **kw):
        return dict(app=self.app,
                    allow_config=True,
                    checkout_url=self.app.config.options.get('checkout_url'))

    @without_trailing_slash
    @expose()
    @require_post()
    def set_checkout_url(self, **post_data):
        self.app.config.options['checkout_url'] = post_data['checkout_url']
