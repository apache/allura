import logging

import pkg_resources
from pylons import c, response
from tg import expose, validate, config, redirect
from tg.decorators import with_trailing_slash
from paste.deploy.converters import asbool

from allura.app import Application
from allura import version
from allura.controllers import BaseController

log = logging.getLogger(__name__)

class ForgeActivityApp(Application):
    """Project Activity page for projects."""
    __version__ = version.__version__
    installable = False
    searchable = False
    hidden = True
    sitemap=[]

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = ForgeActivityController()

    def main_menu(self): # pragma no cover
        return []

    def sidebar_menu(self): # pragma no cover
        return []

    def admin_menu(self): # pragma no cover
        return []

    def install(self, project):
        pass # pragma no cover

    def uninstall(self, project):
        pass # pragma no cover


class ForgeActivityController(BaseController):
    @expose('jinja:forgeactivity:templates/index.html')
    @with_trailing_slash
    def index(self, **kw):
        activity_enabled = asbool(config.get('activity_stream.enabled', False))
        if not activity_enabled:
            response.status = 404
            return dict()
        return dict()
