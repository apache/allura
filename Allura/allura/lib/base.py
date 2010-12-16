# -*- coding: utf-8 -*-
"""The base Controller API."""
from threading import local

import pkg_resources
from webob import exc
from tg import TGController, tmpl_context, config
from tg.render import render
from pylons.i18n import _, ungettext, N_
from pylons import c, g
from tw.api import WidgetBunch
from paste.deploy.converters import asbool

from ming.orm.middleware import MingMiddleware

from allura.lib.custom_middleware import ForgeMiddleware

__all__ = ['WsgiDispatchController']

def wsgi_dispatch(environ):
        import allura.model as model
        host = environ['HTTP_HOST'].lower()
        if host == config['oembed.host']:
            from allura.controllers.oembed import OEmbedController
            return OEmbedController()

        neighborhood = model.Neighborhood.query.get(url_prefix='//' + host + '/')
        if neighborhood:
            from allura.controllers.project import HostNeighborhoodController
            return HostNeighborhoodController(neighborhood.name, neighborhood.shortname_prefix)

        if environ['PATH_INFO'].startswith('/_wsgi_/'):
            for ep in pkg_resources.iter_entry_points('allura'):
                App = ep.load()
                if App.wsgi and App.wsgi.handles(environ): return App.wsgi

        return None

class WsgiDispatchController(TGController):
    """
    Base class for the controllers in the application.

    Your web application should have one of these. The root of
    your application is used to compute URLs used by your app.

    """

    def __init__(self):
        self._app = self._base_app
        self._app = MingMiddleware(self._app)
        self._app = ForgeMiddleware(self._app)

    def _base_app(self, environ, start_response):
        if asbool(environ.get('HTTP_X_SFINC_SSL', 'false')):
            environ['wsgi.url_scheme'] = 'https'
        self._setup_request()
        app = self._wsgi_handler(environ)
        if app is None:
            app = lambda e,s: TGController.__call__(self, e, s)
        return app(environ, start_response)

    def _wsgi_handler(self, environ):
        # Have to move out of class in the attemp to break
        # dependency loop between superclass and subclasses.
        return wsgi_dispatch(environ)

    def _setup_request(self):
        '''Responsible for setting all the values we need to be set on pylons.c'''
        raise NotImplementedError, '_setup_request'

    def __call__(self, environ, start_response):
        return self._app(environ, start_response)

