#-*- python -*-
import logging

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, response, config
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import g, c, request

from pymongo.bson import ObjectId

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib import helpers as h
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole
from pyforge.controllers import BaseController

# Local imports
from forgedownloads import version

from pyforge.ext.sfx.lib.sfx_api import SFXProjectApi

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

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = DownloadAdminController(self)

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        url='/downloads/' + c.project.get_tool_data('sfx', 'unix_group_name') + '/'
        return [SitemapEntry(menu_id, url)[self.sidebar_menu()] ]

    def sidebar_menu(self):
        return []

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = super(ForgeDownloadsApp, self).admin_menu()
        if has_artifact_access('configure', app=self)():
            links.append(SitemapEntry('Options', admin_url + 'options', className='nav_child'))
        return links

    def install(self, project):
        'Set up any default permissions and roles here'
        super(ForgeDownloadsApp, self).install(project)
        # Setup permissions
        role_anon = ProjectRole.query.get(name='*anonymous')._id
        c.project.show_download_button = True
        self.config.acl.update(
            configure=c.project.acl['tool'],
            read=[role_anon])

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
        require(has_artifact_access('admin', app=self.app), 'Admin access required')

    @with_trailing_slash
    def index(self, **kw):
        redirect('options')

    @expose('forgedownloads.templates.admin_options')
    def options(self):
        return dict(app=self.app,
                    allow_config=has_artifact_access('configure', app=self.app)())

    @h.vardec
    @expose()
    def update_options(self, **kw):
        show_download_button = kw.pop('show_download_button', '')
        if bool(show_download_button) != c.project.show_download_button:
            h.log_action(log, 'update project download button').info('')
            c.project.show_download_button = bool(show_download_button)
        redirect(request.referrer)
