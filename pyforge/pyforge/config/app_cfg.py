# -*- coding: utf-8 -*-
"""
Global configuration file for TG2-specific settings in pyforge.

This file complements development/deployment.ini.

Please note that **all the argument values are strings**. If you want to
convert them into boolean, for example, you should use the
:func:`paste.deploy.converters.asbool` function, as in::
    
    from paste.deploy.converters import asbool
    setting = asbool(global_conf.get('the_setting'))
 
"""

from tg.configuration import AppConfig, config

import pyforge
from pyforge import model
from pyforge.lib import app_globals, helpers
from pylons.middleware import StatusCodeRedirect

class ForgeConfig(AppConfig):

    def __init__(self):
        AppConfig.__init__(self)
        self.package = pyforge
        self.renderers = [ 'json', 'genshi' ]
        self.default_renderer = 'genshi'
        self.use_sqlalchemy = False
        self.use_toscawidgets = False
        self.use_transaction_manager = False
        self.handle_status_codes = [ 403, 404 ]

    def add_error_middleware(self, global_conf, app):
        app = AppConfig.add_error_middleware(self, global_conf, app)
        app = StatusCodeRedirect(app, [401], '/login')
        return app

base_config = ForgeConfig()
