import logging
from datetime import datetime, timedelta

from pylons import c
from tg.decorators import with_trailing_slash
from formencode import validators as V

from pyforge import version
from pyforge.app import Application
from pyforge.lib.decorators import react
from pyforge.lib import search
from pyforge import model as M

from .lib.sfx_api import SFXProjectApi

log = logging.getLogger(__name__)

class SFXApp(Application):
    '''Handles reflecting project changes over to SFX'''
    __version__ = version.__version__
    installable = False
    sitemap=[]
    root=None
    templates=None

    @classmethod
    @react('forge.project_created')
    def project_created(cls, routing_key, doc):
        api = SFXProjectApi()
        api.create(c.project)

    @classmethod
    @react('forge.project_updated')
    def project_updated(cls, routing_key, doc):
        api = SFXProjectApi()
        api.update(c.project)

    @classmethod
    @react('forge.project_deleted')
    def project_deleted(cls, routing_key, doc):
        api = SFXProjectApi()
        api.delete(c.project)

    def sidebar_menu(self):
        return [ ]

    def admin_menu(self):
        return []

    def install(self, project):
        pass # pragma no cover

    def uninstall(self, project):
        pass # pragma no cover

