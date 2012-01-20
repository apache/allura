#-*- python -*-
import logging

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, response, config, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import g, c, request

# Pyforge-specific imports
from allura.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from allura.lib import helpers as h
from allura.lib.security import has_access, require_access
from allura.lib.decorators import require_post
from allura.lib.utils import permanent_redirect
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

    def main_menu(self):
        '''Apps should provide their entries to be added to the main nav
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        '''
        return [ SitemapEntry(
                self.config.options.mount_label.title(),
                '.')]

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        url='/projects/' + c.project.get_tool_data('sfx', 'unix_group_name') + '/files/'
        return [SitemapEntry(menu_id, url)[self.sidebar_menu()] ]

    def sidebar_menu(self):
        return []

    def admin_menu(self):
        return super(ForgeDownloadsApp, self).admin_menu()

    def install(self, project):
        'Set up any default permissions and roles here'
        super(ForgeDownloadsApp, self).install(project)
        # Setup permissions
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_anon = M.ProjectRole.anonymous()._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_admin, 'configure'),
            ]

class RootController(BaseController):

    def __init__(self):
        setattr(self, 'nav.json', self.nav)

    @expose()
    @with_trailing_slash
    def index(self, **kw):
        url='/projects/' + c.project.get_tool_data('sfx', 'unix_group_name') + '/files/'
        permanent_redirect(url)

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

