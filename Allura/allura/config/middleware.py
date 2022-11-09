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

import ast
import importlib
import mimetypes
import pickle
import six
import tg
import tg.error
import pkg_resources
from tg import config
from paste.deploy.converters import asbool, aslist, asint
from tg.support.registry import RegistryManager
from tg.support.middlewares import StatusCodeRedirect
from beaker.middleware import SessionMiddleware
from beaker.util import PickleSerializer
from paste.exceptions.errormiddleware import ErrorMiddleware
from werkzeug.debug import DebuggedApplication

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

from allura.config.app_cfg import base_config, AlluraJinjaRenderer  # noqa: E402
from allura.config.environment import load_environment  # noqa: E402
from allura.config.app_cfg import ForgeConfig  # noqa: E402
from allura.lib.custom_middleware import AlluraTimerMiddleware  # noqa: E402
from allura.lib.custom_middleware import SSLMiddleware  # noqa: E402
from allura.lib.custom_middleware import StaticFilesMiddleware  # noqa: E402
from allura.lib.custom_middleware import CSRFMiddleware  # noqa: E402
from allura.lib.custom_middleware import CORSMiddleware  # noqa: E402
from allura.lib.custom_middleware import LoginRedirectMiddleware  # noqa: E402
from allura.lib.custom_middleware import RememberLoginMiddleware  # noqa: E402
from allura.lib.custom_middleware import SetRequestHostFromConfig  # noqa: E402
from allura.lib.custom_middleware import MingTaskSessionSetupMiddleware  # noqa: E402
from allura.lib.custom_middleware import ContentSecurityPolicyMiddleware  # noqa: E402
from allura.lib import helpers as h  # noqa: E402
from allura.lib.utils import configure_ming  # noqa: E402

__all__ = ['make_app']


def make_app(global_conf, full_stack=True, **app_conf):
    override_root_module_name = app_conf.get('override_root', None)
    if override_root_module_name:
        # get an actual instance of it, like BasetestProjectRootController or TaskController
        className = override_root_module_name.title().replace('_', '') + 'Controller'
        module = importlib.import_module(f'allura.controllers.{override_root_module_name}')
        rootClass = getattr(module, className)
        root = rootClass()
    else:
        root = None  # will default to RootController in root.py
    return _make_core_app(root, global_conf, full_stack, **app_conf)


class BeakerPickleSerializerWithLatin1(PickleSerializer):
    def loads(self, data_string):
        # need latin1 to decode py2 timestamps in py  https://docs.python.org/3/library/pickle.html#pickle.Unpickler
        return pickle.loads(data_string, **{'encoding': 'latin1'} if six.PY3 else {})


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
    mimetypes.init([pkg_resources.resource_filename('allura', 'etc/mime.types')] + mimetypes.knownfiles)

    # Configure MongoDB
    configure_ming(app_conf)

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

    # Configure the TG environment
    load_environment(global_conf, app_conf)

    app = tg.TGApp()

    for mw_ep in h.iter_entry_points('allura.middleware'):
        Middleware = mw_ep.load()
        if getattr(Middleware, 'when', 'inner') == 'inner':
            app = Middleware(app, config)
    # CSP headers
    app = ContentSecurityPolicyMiddleware(app, config)
    # Required for sessions
    app = SessionMiddleware(app, config, data_serializer=BeakerPickleSerializerWithLatin1())
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
                            app_conf.get('force_ssl.pattern'))
    # Setup resource manager, widget context SOP
    app = ew.WidgetMiddleware(
        app,
        compress=True,
        use_cache=not asbool(global_conf['debug']),
        script_name=app_conf.get('ew.script_name', '/_ew_resources/'),
        url_base=app_conf.get('ew.url_base', '/_ew_resources/'),
        extra_headers=ast.literal_eval(app_conf.get('ew.extra_headers', '[]')),
        cache_max_age=asint(app_conf.get('ew.cache_header_seconds', 60*60*24*365)),

        # settings to pass through to jinja Environment for EW core widgets
        # these are for the easywidgets' own [easy_widgets.engines] entry point
        # (the Allura [easy_widgets.engines] entry point is named "jinja" (not jinja2) but it doesn't need
        #  any settings since it is a class that uses the same jinja env as the rest of allura)
        **{
            'jinja2.auto_reload': asbool(config['auto_reload_templates']),
            'jinja2.bytecode_cache': AlluraJinjaRenderer._setup_bytecode_cache(),
            'jinja2.cache_size': asint(config.get('jinja_cache_size', -1)),
        }
    )
    # Handle static files (by tool)
    app = StaticFilesMiddleware(app, app_conf.get('static.script_name'))
    # Handle setup and flushing of Ming ORM sessions
    app = MingTaskSessionSetupMiddleware(app)
    app = MingMiddleware(app)
    # Set up the registry for stacked object proxies (SOPs).
    #    streaming=true ensures they won't be cleaned up till
    #    the WSGI application's iterator is exhausted
    app = RegistryManager(app, streaming=True)

    # "task" wsgi would get a 2nd request to /error/document if we used this middleware
    if config.get('override_root') not in ('task', 'basetest_project_root'):
        if asbool(config['debug']):
            # Converts exceptions to HTTP errors, shows traceback in debug mode
            app = DebuggedApplication(app, evalex=True)
        else:
            app = ErrorMiddleware(app, config, **config['tg.errorware'])

        app = SetRequestHostFromConfig(app, config)

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
    import tg
    from allura.lib import helpers as h
    from six.moves.urllib.parse import quote, quote_plus
    context.setdefault('g', tg.app_globals)
    context.setdefault('c', tg.tmpl_context)
    context.setdefault('h', h)
    context.setdefault('request', tg.request)
    context.setdefault('response', tg.response)
    context.setdefault('url', tg.url)
    context.setdefault('tg', dict(
        config=tg.config,
        flash_obj=tg.flash,
        quote=quote,
        quote_plus=quote_plus,
        url=tg.url))
