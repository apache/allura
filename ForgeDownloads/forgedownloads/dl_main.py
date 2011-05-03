#-*- python -*-
import logging

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, response, config, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import g, c, request

# Pyforge-specific imports
from allura.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from allura.lib import helpers as h
from allura.lib.security import has_access, require_access
from allura.lib.decorators import require_post
from allura import model as M
from allura.controllers import BaseController

# Local imports
from forgedownloads import version

log = logging.getLogger(__name__)


class ForgeDownloadsApp(Application):
    __version__ = version.__version__
    permissions = [ 'configure', 'read' ]
    searchable=True
    # installable=config['auth.method'] == 'sfx'
    templates=None
    tool_label='Downloads'
    default_mount_label='Downloads'
    default_mount_point='downloads'
    ordinal=8
    icons={
        24:'images/downloads_24.png',
        32:'images/downloads_32.png',
        48:'images/downloads_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = DownloadAdminController(self)

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        url='/projects/' + c.project.get_tool_data('sfx', 'unix_group_name') + '/files/'
        return [SitemapEntry(menu_id, url)[self.sidebar_menu()] ]

    def sidebar_menu(self):
        return []

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = super(ForgeDownloadsApp, self).admin_menu()
        if has_access(self, 'configure')():
            links.append(SitemapEntry('Options', admin_url + 'options', className='admin_modal'))
        return links

    def install(self, project):
        'Set up any default permissions and roles here'
        super(ForgeDownloadsApp, self).install(project)
        c.project.show_download_button = True
        # Setup permissions
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_anon = M.ProjectRole.anonymous()._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_admin, 'configure'),
            ]

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        c.project.show_download_button = False
        super(ForgeDownloadsApp, self).uninstall(project)

class RootController(BaseController):

    def __init__(self):
        setattr(self, 'nav.json', self.nav)

    @expose('json:')
    def nav(self):
        if c.app.sitemap:
            my_entry = c.app.sitemap[0]
        else:
            my_entry = None
        def _entry(s):
            d = dict(name=s.label, url=s.url, icon=s.ui_icon)
            if my_entry and s.url == my_entry.url:
                d['selected'] = True
            return d
        return dict(menu=[ _entry(s) for s in c.project.sitemap() ] )

class DownloadAdminController(DefaultAdminController):

    def _check_security(self):
        require_access(self.app, 'configure')

    @with_trailing_slash
    def index(self, **kw):
        redirect('options')

    @expose('jinja:forgedownloads:templates/downloads/admin_options.html')
    def options(self):
        return dict(app=self.app,
                    allow_config=has_access(self.app, 'configure')())

    @h.vardec
    @expose()
    @require_post()
    def update_options(self, **kw):
        show_download_button = kw.pop('show_download_button', '')
        if bool(show_download_button) != c.project.show_download_button:
            h.log_action(log, 'update project download button').info('')
            c.project.show_download_button = bool(show_download_button)
        flash('Download options updated')
        redirect(c.project.url()+'admin/tools')
