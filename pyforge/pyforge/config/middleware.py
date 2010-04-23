# -*- coding: utf-8 -*-
"""WSGI middleware initialization for the pyforge application."""

from webob import exc
from tg import redirect
from paste.deploy.converters import asbool

import ew

from pyforge.config.app_cfg import base_config
from pyforge.config.environment import load_environment
from pyforge.config.app_cfg import ForgeConfig
__all__ = ['make_app']

# Use base_config to setup the necessary PasteDeploy application factory. 
# make_base_app will wrap the TG2 app with all the middleware it needs. 
make_base_app = base_config.setup_tg_wsgi_app(load_environment)


def make_app(global_conf, full_stack=True, **app_conf):
    """
    Set pyforge up with the settings found in the PasteDeploy configuration
    file used.
    
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
    # Create base app
    app = make_base_app(global_conf, full_stack=True, **app_conf)
    # Configure MongoDB
    import ming
    ming.configure(**app_conf)
    # Wrap your base TurboGears 2 application with custom middleware here
    if hasattr(ew.ResourceManager, 'configure'):
        # ew.ResourceManager.configure(compress=not asbool(global_conf['debug']))
        ew.ResourceManager.configure(compress=False)
    ew.ResourceManager.register_all_resources()
    return app

def make_plugin_test_app(global_conf, full_stack=True, **app_conf):
    base_config = ForgeConfig('test')
    load_environment = base_config.make_load_environment()
    make_base_app = base_config.setup_tg_wsgi_app(load_environment)

    # Create base app
    app = make_base_app(global_conf, full_stack=True, **app_conf)
    # Configure MongoDB
    import ming
    ming.configure(**app_conf)
    # Wrap your base TurboGears 2 application with custom middleware here
    return app
    
