# -*- coding: utf-8 -*-
"""WSGI middleware initialization for the allura application."""
import mimetypes

import tg
import pkg_resources
from tg import config
from paste.deploy.converters import asbool
from paste.registry import RegistryManager
from beaker.middleware import SessionMiddleware
from routes.middleware import RoutesMiddleware
from pylons.middleware import StatusCodeRedirect

import ew
import ming
from ming.orm.middleware import MingMiddleware

from allura.config.app_cfg import base_config
from allura.config.environment import load_environment
from allura.config.app_cfg import ForgeConfig
from allura.lib.custom_middleware import StatsMiddleware
from allura.lib.custom_middleware import SSLMiddleware
from allura.lib.custom_middleware import StaticFilesMiddleware
from allura.lib.custom_middleware import CSRFMiddleware
from allura.lib.custom_middleware import LoginRedirectMiddleware
from allura.lib import patches
from allura.lib import helpers as h

__all__ = ['make_app']

# Use base_config to setup the necessary PasteDeploy application factory. 
# make_base_app will wrap the TG2 app with all the middleware it needs. 
make_base_app = base_config.setup_tg_wsgi_app(load_environment)


def make_app(global_conf, full_stack=True, **app_conf):
    root = app_conf.get('override_root', 'root')
    return _make_core_app(root, global_conf, full_stack, **app_conf)

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
    # Run all the initialization code here
    mimetypes.init(
        [pkg_resources.resource_filename('allura', 'etc/mime.types')]
        + mimetypes.knownfiles)
    patches.apply()
    # Configure MongoDB
    ming.configure(**app_conf)

    # Configure EW variable provider
    ew.render.TemplateEngine.register_variable_provider(get_tg_vars)
    
    # Create base app
    base_config = ForgeConfig(root)
    load_environment = base_config.make_load_environment()

    # Code adapted from tg.configuration, replacing the following lines:
    #     make_base_app = base_config.setup_tg_wsgi_app(load_environment)
    #     app = make_base_app(global_conf, full_stack=True, **app_conf)

    # Configure the Pylons environment
    load_environment(global_conf, app_conf)

    app = tg.TGApp()
    if asbool(config.get('auth.method', 'local')=='sfx'):
        import sfx.middleware
        d = h.config_with_prefix(config, 'auth.')
        d.update(h.config_with_prefix(config, 'sfx.'))
        app = sfx.middleware.SfxMiddleware(app, d)
    # Required for pylons
    app = RoutesMiddleware(app, config['routes.map'])
    # Required for sessions
    app = SessionMiddleware(app, config)
    # Converts exceptions to HTTP errors, shows traceback in debug mode
    app = tg.error.ErrorHandler(app, global_conf, **config['pylons.errorware'])
    # Redirect some status codes to /error/document
    if asbool(config['debug']):
        app = StatusCodeRedirect(app, base_config.handle_status_codes)
    else:
        app = StatusCodeRedirect(app, base_config.handle_status_codes + [500])
    # Redirect 401 to the login page
    app = LoginRedirectMiddleware(app)
    # Add instrumentation
    if app_conf.get('stats.sample_rate', '0.25') != '0':
        stats_config = dict(global_conf, **app_conf)
        app = StatsMiddleware(app, stats_config)
    # Clear cookies when the CSRF field isn't posted
    if not app_conf.get('disable_csrf_protection'):
        app = CSRFMiddleware(app, '_session_id')
    # Setup the allura SOPs
    app = allura_globals_middleware(app)
    # Ensure https for logged in users, http for anonymous ones
    if asbool(app_conf.get('auth.method', 'local')=='sfx'):
        app = SSLMiddleware(app, app_conf.get('no_redirect.pattern'))
    # Setup resource manager, widget context SOP
    app = ew.WidgetMiddleware(
        app,
        compress=not asbool(global_conf['debug']),
        # compress=True,
        script_name=app_conf.get('ew.script_name', '/_ew_resources/'),
        url_base=app_conf.get('ew.url_base', '/_ew_resources/'))
    # Make sure that the wsgi.scheme is set appropriately when we
    # have the funky HTTP_X_SFINC_SSL  environ var
    if asbool(app_conf.get('auth.method', 'local')=='sfx'):
        app = set_scheme_middleware(app)
    # Handle static files (by tool)
    app = StaticFilesMiddleware(app, app_conf.get('static.script_name'))
    # Handle setup and flushing of Ming ORM sessions
    app = MingMiddleware(app)
    # Set up the registry for stacked object proxies (SOPs).
    #    streaming=true ensures they won't be cleaned up till
    #    the WSGI application's iterator is exhausted
    app = RegistryManager(app, streaming=True)
    return app
    
def set_scheme_middleware(app):
    def SchemeMiddleware(environ, start_response):
        if asbool(environ.get('HTTP_X_SFINC_SSL', 'false')):
            environ['wsgi.url_scheme'] = 'https'
        return app(environ, start_response)
    return SchemeMiddleware

def allura_globals_middleware(app):
    def AlluraGlobalsMiddleware(environ, start_response):
        from allura import credentials
        from allura.lib import security, app_globals
        from tg import tg_globals
        registry = environ['paste.registry']
        registry.register(credentials, security.Credentials())
        registry.register(tg_globals.environ, environ)
        registry.register(tg_globals.c, EmptyClass())
        registry.register(tg_globals.g, app_globals.Globals())
        return app(environ, start_response)
    return AlluraGlobalsMiddleware

class EmptyClass(object): pass

def get_tg_vars(context):
    import pylons, tg
    from allura.lib import helpers as h
    from urllib import quote, quote_plus
    context.setdefault('g', pylons.g)
    context.setdefault('c', pylons.c)
    context.setdefault('h', h)
    context.setdefault('request', pylons.request)
    context.setdefault('response', pylons.response)
    context.setdefault('url', pylons.url)
    context.setdefault('tg', dict(
            config=tg.config,
            flash_obj=tg.flash,
            quote=quote,
            quote_plus=quote_plus,
            url=tg.url))
