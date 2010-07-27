#-*- python -*-
import logging
import sys
import shutil

sys.path.append('/usr/lib/python2.6/dist-packages')

# Non-stdlib imports
import pkg_resources
from pylons import c, g
from tg import redirect, expose
from tg.decorators import with_trailing_slash, without_trailing_slash

# Pyforge-specific imports
from pyforge import model as M
from pyforge.app import Application, SitemapEntry, DefaultAdminController
from pyforge.lib import helpers as h
from pyforge.lib.decorators import audit
from pyforge.lib.security import has_artifact_access

# Local imports
from forgesvn import model
from forgesvn import version
from .reactors import reactors
from .controllers import BranchBrowser

log = logging.getLogger(__name__)

class ForgeSVNApp(Application):
    '''This is the SVN app for PyForge'''
    __version__ = version.__version__
    permissions = [ 'read', 'write', 'create', 'admin', 'configure' ]
    tool_label='SVN'
    default_mount_label='SVN'
    default_mount_point='svn'
    ordinal=4

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = BranchBrowser()
        self.admin = SVNAdminController(self)

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = [SitemapEntry('Viewable Files', admin_url + 'extensions', className='nav_child')]
        # if self.permissions and has_artifact_access('configure', app=self)():
        #     links.append(SitemapEntry('Permissions', admin_url + 'permissions', className='nav_child'))
        return links

    def sidebar_menu(self):
        links = [ SitemapEntry('Home',c.app.url, ui_icon='home') ]
        if c.app.repo.latest:
            links.append(SitemapEntry('Browse',c.app.url+"LATEST/tree/", ui_icon='folder-collapsed'))
            links.append(SitemapEntry('Log',c.app.url+"log/", ui_icon='document-b'))
        if has_artifact_access('admin', app=c.app)():
            links.append(SitemapEntry('Admin', c.project.url()+'admin/'+self.config.options.mount_point, ui_icon='tool-admin'))
        return links

    @property
    def repo(self):
        return model.SVNRepository.query.get(app_config_id=self.config._id)

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgesvn', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project.name
        super(ForgeSVNApp, self).install(project)
        # Setup permissions
        role_developer = M.ProjectRole.query.get(name='Developer')._id
        self.config.acl.update(
            configure=c.project.acl['tool'],
            read=c.project.acl['read'],
            create=[role_developer],
            write=[role_developer],
            admin=c.project.acl['tool'])
        repo = model.SVNRepository(
            name=self.config.options.mount_point,
            tool = 'svn',
            status = 'creating')
        g.publish('audit', 'scm.svn.init', dict(repo_name=repo.name, repo_path=repo.fs_path))

    def uninstall(self, project):
        g.publish('audit', 'scm.svn.uninstall', dict(project_id=project._id))

    @audit('scm.svn.uninstall')
    def _uninstall(self, routing_key, data):
        "Remove all the tool's artifacts and the physical repository"
        repo = self.repo
        if repo is not None:
            shutil.rmtree(repo.full_fs_path, ignore_errors=True)
        model.SVNRepository.query.remove(dict(app_config_id=self.config._id))
        super(ForgeSVNApp, self).uninstall(project_id=data['project_id'])


class SVNAdminController(DefaultAdminController):

    def __init__(self, app):
        self.app = app
        self.repo = app.repo

    @with_trailing_slash
    def index(self, **kw):
        redirect('permissions')

    @without_trailing_slash
    @expose('forgesvn.templates.admin_extensions')
    def extensions(self, **kw):
        return dict(app=self.app,
                    allow_config=has_artifact_access('configure', app=self.app)(),
                    additional_viewable_extensions=getattr(self.repo, 'additional_viewable_extensions', ''))

    @without_trailing_slash
    @expose()
    def set_extensions(self, **post_data):
        self.repo.additional_viewable_extensions = post_data['additional_viewable_extensions']

h.mixin_reactors(ForgeSVNApp, reactors)
