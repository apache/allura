 #-*- python -*-
import logging

# Pyforge-specific imports
from allura.app import Application
from allura.lib.helpers import mixin_reactors

# Local imports
from . import version
from .reactors import common_react

log = logging.getLogger(__name__)

class ForgeMailApp(Application):
    '''Reactor-only app'''
    __version__ = version.__version__
    wsgi=None
    installable=False
    sitemap = []
    sidebar_menu = []
    tool_label='Mail'
    default_mount_label='Mail'
    default_mount_point='mail'
    ordinal=0

    def install(self, project):
        raise NotImplemented, 'install'

    def uninstall(self, project):
        raise NotImplemented, 'install'

mixin_reactors(ForgeMailApp, common_react)


