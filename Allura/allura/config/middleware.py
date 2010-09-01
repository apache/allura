# -*- coding: utf-8 -*-
"""WSGI middleware initialization for the allura application."""
import mimetypes

import pkg_resources
from webob import exc
from tg import redirect
from paste.deploy.converters import asbool

import ew
import ming

from allura.config.app_cfg import base_config
from allura.config.environment import load_environment
from allura.config.app_cfg import ForgeConfig
from allura.lib.custom_middleware import StatsMiddleware
from allura.lib.custom_middleware import SSLMiddleware
from allura.lib.custom_middleware import StaticFilesMiddleware
from allura.lib import patches

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
    Set allura up with the settings found in the PasteDeploy configuration
    file used.

    :param root: The controller module containing the TG root
    :param global_conf: The global settings for allura (those
        defined under the ``[DEFAULT]`` section).
    :type global_conf: dict
    :param full_stack: Should the whole TG2 stack be set up?
    :type full_stack: str or bool
    :return: The allura application with all the relevant middleware
        loaded.
    
    This is the PasteDeploy factory for the allura application.
    
    ``app_conf`` contains all the application-specific settings (those defined
    under ``[app:main]``.
    
   
    """
    mimetypes.init(
        [pkg_resources.resource_filename('allura', 'etc/mime.types')]
        + mimetypes.knownfiles)
    patches.apply()
    
    # Create base app
    base_config = ForgeConfig(root)
    load_environment = base_config.make_load_environment()
    make_base_app = base_config.setup_tg_wsgi_app(load_environment)
    app = make_base_app(global_conf, full_stack=True, **app_conf)

    # Configure MongoDB
    ming.configure(**app_conf)

    # Wrap your base TurboGears 2 application with custom middleware here
    # app = MingMiddleware(app)
    if app_conf.get('stats.sample_rate', '0.25') != '0':
        stats_config = dict(global_conf, **app_conf)
        app = StatsMiddleware(app, stats_config)

    if asbool(app_conf.get('auth.method', 'local')=='sfx'):
        app = SSLMiddleware(app, app_conf.get('no_redirect.pattern'))

    app = ew.ResourceMiddleware(
        app,
        compress=not asbool(global_conf['debug']),
        # compress=True,
        script_name=app_conf.get('ew.script_name', '/_ew_resources/'),
        url_base=app_conf.get('ew.url_base', '/_ew_resources/'))

    app = StaticFilesMiddleware(app, app_conf.get('static.script_name'))

    return app
    

