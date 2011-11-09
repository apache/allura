#-*- python -*-
import logging
from pylons import c, request

# Non-stdlib imports
from ming.utils import LazyProperty
from ming.orm.ormsession import ThreadLocalORMSession
from tg import expose, redirect, validate, flash
from tg.decorators import with_trailing_slash, without_trailing_slash

# Pyforge-specific imports
import allura.tasks.repo_tasks
from allura.controllers import BaseController
from allura.controllers.repository import RepoRootController
from allura.lib.decorators import require_post
from allura.lib.repository import RepositoryApp, RepoAdminController
from allura.app import SitemapEntry, ConfigOption
from allura.lib import helpers as h
from allura import model as M

# Local imports
from . import model as SM
from . import version
from . import widgets
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
        links.append(SitemapEntry(
                'Checkout URL',
                c.project.url()+'admin/'+self.config.options.mount_point+'/' + 'checkout_url',
                className='admin_modal'))
        links.append(SitemapEntry(
                'Import Repo',
                c.project.url()+'admin/'+self.config.options.mount_point+'/' + 'importer/'))
        return links

class SVNRepoAdminController(RepoAdminController):
    def __init__(self, app):
        super(SVNRepoAdminController, self).__init__(app)
        self.importer = SVNImportController(self.app)

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

class SVNImportController(BaseController):
    import_form=widgets.ImportForm()

    def __init__(self, app):
        self.app = app

    @with_trailing_slash
    @expose('jinja:forgesvn:templates/svn/import.html')
    def index(self, **kw):
        c.form = self.import_form
        return dict()

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(import_form, error_handler=index)
    def do_import(self, checkout_url=None, **kwargs):
        with h.push_context(
            self.app.config.project_id,
            app_config_id=self.app.config._id):
            allura.tasks.repo_tasks.reclone.post(
                cloned_from_path=None,
                cloned_from_name=None,
                cloned_from_url=checkout_url)
        M.Notification.post_user(
            c.user, self.app.repo, 'importing',
            text='Repository import scheduled')
        redirect(c.project.url() + 'admin/tools')
