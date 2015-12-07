# -*- coding: utf-8 -*-

#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

"""WSGI middleware initialization for the allura application."""
import mimetypes

import pylons.middleware
import tg
import tg.error
import pkg_resources
from tg import config
from paste.deploy.converters import asbool, aslist, asint
from paste.registry import RegistryManager
from routes.middleware import RoutesMiddleware
from pylons.middleware import StatusCodeRedirect
from beaker.middleware import SessionMiddleware

import activitystream
import ew
import formencode
import ming
from ming.orm.middleware import MingMiddleware

# Must apply patches before other Allura imports to ensure all the patches are effective.
# This file gets imported from paste/deploy/loadwsgi.py pretty early in the app execution
from allura.lib import patches
patches.apply()
try:
    import newrelic
except ImportError:
    pass
else:
    patches.newrelic()

from allura.config.app_cfg import base_config
from allura.config.environment import load_environment
from allura.config.app_cfg import ForgeConfig
from allura.lib.custom_middleware import AlluraTimerMiddleware
from allura.lib.custom_middleware import SSLMiddleware
from allura.lib.custom_middleware import StaticFilesMiddleware
from allura.lib.custom_middleware import CSRFMiddleware
from allura.lib.custom_middleware import CORSMiddleware
from allura.lib.custom_middleware import LoginRedirectMiddleware
from allura.lib.custom_middleware import RememberLoginMiddleware
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

    # Configure MongoDB
    ming.configure(**app_conf)

    # Configure ActivityStream
    if asbool(app_conf.get('activitystream.recording.enabled', False)):
        activitystream.configure(**h.convert_bools(app_conf, prefix='activitystream.'))

    # Configure EW variable provider
    ew.render.TemplateEngine.register_variable_provider(get_tg_vars)

    # Set FormEncode language to english, as we don't support any other locales
    formencode.api.set_stdtranslation(domain='FormEncode', languages=['en'])

    # Create base app
    base_config = ForgeConfig(root)
    load_environment = base_config.make_load_environment()

    # Code adapted from tg.configuration, replacing the following lines:
    #     make_base_app = base_config.setup_tg_wsgi_app(load_environment)
    #     app = make_base_app(global_conf, full_stack=True, **app_conf)

    # Configure the Pylons environment
    load_environment(global_conf, app_conf)

    app = tg.TGApp()

    for mw_ep in h.iter_entry_points('allura.middleware'):
        Middleware = mw_ep.load()
        if getattr(Middleware, 'when', 'inner') == 'inner':
            app = Middleware(app, config)

    # Required for pylons
    app = RoutesMiddleware(app, config['routes.map'])
    # Required for sessions
    app = SessionMiddleware(app, config)
    # Handle "Remember me" functionality
    app = RememberLoginMiddleware(app, config)
    # Redirect 401 to the login page
    app = LoginRedirectMiddleware(app)
    # Add instrumentation
    app = AlluraTimerMiddleware(app, app_conf)
    # Clear cookies when the CSRF field isn't posted
    if not app_conf.get('disable_csrf_protection'):
        app = CSRFMiddleware(app, '_session_id')
    if asbool(config.get('cors.enabled', False)):
        # Handle CORS requests
        allowed_methods = aslist(config.get('cors.methods'))
        allowed_headers = aslist(config.get('cors.headers'))
        cache_duration = asint(config.get('cors.cache_duration', 0))
        app = CORSMiddleware(app, allowed_methods, allowed_headers, cache_duration)
    # Setup the allura SOPs
    app = allura_globals_middleware(app)
    # Ensure http and https used per config
    if config.get('override_root') != 'task':
        app = SSLMiddleware(app, app_conf.get('no_redirect.pattern'),
                            app_conf.get('force_ssl.pattern'),
                            app_conf.get('force_ssl.logged_in'))
    # Setup resource manager, widget context SOP
    app = ew.WidgetMiddleware(
        app,
        compress=not asbool(global_conf['debug']),
        # compress=True,
        script_name=app_conf.get('ew.script_name', '/_ew_resources/'),
        url_base=app_conf.get('ew.url_base', '/_ew_resources/'),
        extra_headers=eval(app_conf.get('ew.extra_headers', 'None')),
        cache_max_age=asint(app_conf.get('ew.cache_header_seconds', 60*60*24*365)),
    )
    # Handle static files (by tool)
    app = StaticFilesMiddleware(app, app_conf.get('static.script_name'))
    # Handle setup and flushing of Ming ORM sessions
    app = MingMiddleware(app)
    # Set up the registry for stacked object proxies (SOPs).
    #    streaming=true ensures they won't be cleaned up till
    #    the WSGI application's iterator is exhausted
    app = RegistryManager(app, streaming=True)

    # "task" wsgi would get a 2nd request to /error/document if we used this middleware
    if config.get('override_root') != 'task':
        # Converts exceptions to HTTP errors, shows traceback in debug mode
        # don't use TG footer with extra CSS & images that take time to load
        tg.error.footer_html = '<!-- %s %s -->'
        app = tg.error.ErrorHandler(
            app, global_conf, **config['pylons.errorware'])

        # Redirect some status codes to /error/document
        if asbool(config['debug']):
            app = StatusCodeRedirect(app, base_config.handle_status_codes)
        else:
            app = StatusCodeRedirect(
                app, base_config.handle_status_codes + [500])

    for mw_ep in h.iter_entry_points('allura.middleware'):
        Middleware = mw_ep.load()
        if getattr(Middleware, 'when', 'inner') == 'outer':
            app = Middleware(app, config)

    return app


def allura_globals_middleware(app):
    def AlluraGlobalsMiddleware(environ, start_response):
        import allura.lib.security
        import allura.lib.app_globals
        registry = environ['paste.registry']
        registry.register(allura.credentials,
                          allura.lib.security.Credentials())
        return app(environ, start_response)
    return AlluraGlobalsMiddleware


def get_tg_vars(context):
    import pylons
    import tg
    from allura.lib import helpers as h
    from urllib import quote, quote_plus
    context.setdefault('g', pylons.app_globals)
    context.setdefault('c', pylons.tmpl_context)
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
