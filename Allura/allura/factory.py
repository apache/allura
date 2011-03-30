import string
import mimetypes

import pkg_resources
from webob import exc
from webhelpers import html
from paste.deploy.converters import asbool
from paste.registry import RegistryManager
from pyramid.config import Configurator
from pyramid.session import UnencryptedCookieSessionFactoryConfig

import ew
import ming
import tg.view
import tg.error
import tg.traversal
from ming.orm.middleware import MingMiddleware
from tg.shim import RootFactory

from allura.lib import helpers as h
from allura.lib.custom_middleware import StatsMiddleware
from allura.lib.custom_middleware import SSLMiddleware
from allura.lib.custom_middleware import StaticFilesMiddleware
from allura.lib.custom_middleware import CSRFMiddleware
from allura.lib.custom_middleware import LoginRedirectMiddleware

def main(global_config, **settings):
    conf = dict(global_config, **settings)
    # Run all the initialization code here
    mimetypes.init(
        [pkg_resources.resource_filename('allura', 'etc/mime.types')]
        + mimetypes.knownfiles)

    # Configure MongoDB
    ming.configure(**settings)

    # Configure EW variable provider
    ew.render.TemplateEngine.initialize(settings)
    ew.render.TemplateEngine.register_variable_provider(get_tg_vars)

    # Create base app
    root = settings.get('override_root', 'allura.controllers.root:RootController')
    config = Configurator(
        root_factory=RootFactory(root),
        settings=settings,
        session_factory=UnencryptedCookieSessionFactoryConfig(
            secret=settings['session.secret'],
            cookie_name=settings['session.key']))
    config.add_view(
        tg.view.tg_view,
        context=tg.traversal.Resource)
    config.add_view(
        tg.view.error_view,
        context=exc.WSGIHTTPException)
    app = config.make_wsgi_app()

    if asbool(conf.get('auth.method', 'local')=='sfx'):
        import sfx.middleware
        d = h.config_with_prefix(config, 'auth.')
        d.update(h.config_with_prefix(config, 'sfx.'))
        app = sfx.middleware.SfxMiddleware(app, d)
    app = tg.error.ErrorHandler(app, global_config)
    # Redirect 401 to the login page
    app = LoginRedirectMiddleware(app)
    # Add instrumentation
    if conf.get('stats.sample_rate', '0.25') != '0':
        app = StatsMiddleware(app, conf)
    # Clear cookies when the CSRF field isn't posted
    if not conf.get('disable_csrf_protection'):
        app = CSRFMiddleware(app, '_session_id')
    # Setup the allura SOPs
    app = allura_globals_middleware(app, conf)
    # Ensure https for logged in users, http for anonymous ones
    if asbool(conf.get('auth.method', 'local')=='sfx'):
        app = SSLMiddleware(app, conf.get('no_redirect.pattern'))
    # Setup resource manager, widget context SOP
    app = ew.WidgetMiddleware(
        app,
        compress=not asbool(conf['debug']),
        # compress=True,
        script_name=conf.get('ew.script_name', '/_ew_resources/'),
        url_base=conf.get('ew.url_base', '/_ew_resources/'))
    # Make sure that the wsgi.scheme is set appropriately when we
    # have the funky HTTP_X_SFINC_SSL  environ var
    if asbool(conf.get('auth.method', 'local')=='sfx'):
        app = set_scheme_middleware(app)
    # Handle static files (by tool)
    app = StaticFilesMiddleware(app, conf.get('static.script_name'))
    # Handle setup and flushing of Ming ORM sessions
    app = MingMiddleware(app)
    # Set up the registry for stacked object proxies (SOPs).
    #    streaming=true ensures they won't be cleaned up till
    #    the WSGI application's iterator is exhausted
    app = RegistryManager(app, streaming=True)
    return app

def allura_globals_middleware(app, conf):
    def AlluraGlobalsMiddleware(environ, start_response):
        from allura import credentials
        from allura.lib import security, app_globals
        from tg import tg_globals
        registry = environ['paste.registry']
        registry.register(tg_globals.config, conf)
        registry.register(credentials, security.Credentials())
        registry.register(tg_globals.environ, environ)
        registry.register(tg_globals.c, _EmptyClass())
        registry.register(tg_globals.g, app_globals.Globals())
        return app(environ, start_response)
    return AlluraGlobalsMiddleware

def set_scheme_middleware(app):
    def SchemeMiddleware(environ, start_response):
        if asbool(environ.get('HTTP_X_SFINC_SSL', 'false')):
            environ['wsgi.url_scheme'] = 'https'
        return app(environ, start_response)
    return SchemeMiddleware

def get_tg_vars(context):
    from tg import c, g, request, response, config, url
    from urllib import quote, quote_plus
    context.setdefault('g', g)
    context.setdefault('c', c)
    context.setdefault('h', h)
    context.setdefault('request', request)
    context.setdefault('response', response)
    context.setdefault('config', config)
    tg = dict(
        url=url,
        quote=quote,
        quote_plus=quote_plus,
        config=config,
        flash_obj=FlashObj(request))
    context.setdefault('tg', tg)

class FlashObj(object):
    full_template = string.Template('<div id="$container_id">$parts</div>')
    part_template = string.Template('<div class="$queue">$message</div>')
    def __init__(self, request):
        try:
            self.impl = request.session
        except AttributeError:
            self.impl = None
    def render(self, container_id, use_js=False):
        if self.impl is None: return ''
        parts = ''
        for queue in ('error', 'warning', ''):
            messages = [ html.escape(msg) for msg in self.impl.pop_flash(queue) ]
            parts += '\n'.join(
                self.part_template.substitute(queue=queue, message=message)
                for message in messages)
        if parts:
            return self.full_template.substitute(
                container_id=container_id,
                parts=parts)
        else:
            return ''

class _EmptyClass(object): pass
