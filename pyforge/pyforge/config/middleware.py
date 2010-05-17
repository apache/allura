# -*- coding: utf-8 -*-
"""WSGI middleware initialization for the pyforge application."""

from webob import exc
from tg import redirect
from paste.deploy.converters import asbool

import ew
import ming

from pyforge.config.app_cfg import base_config
from pyforge.config.environment import load_environment
from pyforge.config.app_cfg import ForgeConfig
from pyforge.lib.custom_middleware import SfxLoginMiddleware, SSLMiddleware

__all__ = ['make_app']

# Use base_config to setup the necessary PasteDeploy application factory. 
# make_base_app will wrap the TG2 app with all the middleware it needs. 
make_base_app = base_config.setup_tg_wsgi_app(load_environment)


def make_app(global_conf, full_stack=True, **app_conf):
    return _make_core_app('root', global_conf, full_stack, **app_conf)

def make_tool_test_app(global_conf, full_stack=True, **app_conf):
    return _make_core_app('test', global_conf, full_stack, **app_conf)

def _make_core_app(root, global_conf, full_stack=True, **app_conf):
    """
    Set pyforge up with the settings found in the PasteDeploy configuration
    file used.

    :param root: The controller module containing the TG root
    :param global_conf: The global settings for pyforge (those
        defined under the ``[DEFAULT]`` section).
    :type global_conf: dict
    :param full_stack: Should the whole TG2 stack be set up?
    :type full_stack: str or bool
    :return: The pyforge application with all the relevant middleware
        loaded.
    
    This is the PasteDeploy factory for the pyforge application.
    
    ``app_conf`` contains all the application-specific settings (those defined
    under ``[app:main]``.
    
   
    """
    import pyforge.lib.helpers as h

    # Create base app
    base_config = ForgeConfig(root)
    load_environment = base_config.make_load_environment()
    make_base_app = base_config.setup_tg_wsgi_app(load_environment)
    app = make_base_app(global_conf, full_stack=True, **app_conf)

    # Configure MongoDB
    ming.configure(**app_conf)

    # Configure EW
    if hasattr(ew.ResourceManager, 'configure'):
        ew.ResourceManager.configure(compress=not asbool(global_conf['debug']))
    ew.ResourceManager.register_all_resources()

    # Wrap your base TurboGears 2 application with custom middleware here
    # app = MingMiddleware(app)

    if asbool(app_conf.get('auth.method', 'local')=='sfx'):
        app = SSLMiddleware(app)

    return app
    

