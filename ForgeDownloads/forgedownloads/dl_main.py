#-*- python -*-
import logging

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, response, config
from pylons import g, c, request

from pymongo.bson import ObjectId

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib import helpers as h
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole

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

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_point.title()
        api = SFXProjectApi()
        url='http://sf.net/downloads/' + api._unix_group_name(c.project.neighborhood, c.project.shortname) + '/'
        return [SitemapEntry(menu_id, url)[self.sidebar_menu()] ]

    def sidebar_menu(self):
        return []

    def admin_menu(self):
        return super(ForgeDownloadsApp, self).admin_menu()

class RootController(object):

    def __init__(self):
        setattr(self, 'nav.json', self.nav)

    @expose('json:')
    def nav(self):
        my_entry = c.app.sitemap[0]
        def _entry(s):
            d = dict(name=s.label, url=s.url, icon=s.ui_icon)
            if s.url == my_entry.url:
                d['selected'] = True
            return d
        return dict(menu=[ _entry(s) for s in c.project.sitemap() ] )
