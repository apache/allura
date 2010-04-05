# -*- coding: utf-8 -*-

"""The base Controller API."""

from tg import TGController, tmpl_context, config
from tg.render import render
from pylons.i18n import _, ungettext, N_
from pylons import c, g
from tw.api import WidgetBunch
import pyforge.model as model

import pkg_resources
from webob import exc
import ming

__all__ = ['BaseController']


class BaseController(TGController):
    """
    Base class for the controllers in the application.

    Your web application should have one of these. The root of
    your application is used to compute URLs used by your app.

    """

    def __call__(self, environ, start_response):
        """This is the basic WSGI callable that wraps and dispatches forge controllers.

        It peforms a number of functions:
          * displays the forge index page
          * sets up and cleans up the Ming/MongoDB Session
          * persists all Ming object changes to Mongo
        """
        environ['wsgi.url_scheme'] = 'https'

        app = self._wsgi_handler(environ)
        if app is None:
            """Invoke the Controller"""
            # TGController.__call__ dispatches to the Controller method
            # the request is routed to. This routing information is
            # available in environ['pylons.routes_dict']
            app = lambda e,s: TGController.__call__(self, e, s)
        try:
            result = app(environ, start_response)
            if not isinstance(result, list):
                return self._cleanup_iterator(result)
            else:
                self._cleanup_request()
                return result
        except exc.HTTPRedirection:
            self._cleanup_request()
            raise
        except:
            ming.orm.ormsession.ThreadLocalORMSession.close_all()
            raise

    def _wsgi_handler(self, environ):
        host = environ['HTTP_HOST'].lower()
        if host == config['oembed.host']:
            return OEmbedController()
        neighborhood = model.Neighborhood.query.get(url_prefix='//' + host + '/')
        if neighborhood:
            return HostNeighborhoodController(neighborhood.name, neighborhood.shortname_prefix)
        if environ['PATH_INFO'].startswith('/_wsgi_/'):
            for ep in pkg_resources.iter_entry_points('pyforge'):
                App = ep.load()
                if App.wsgi and App.wsgi.handles(environ): return App.wsgi

    def _cleanup_request(self):
        ming.orm.ormsession.ThreadLocalORMSession.flush_all()
        ming.orm.ormsession.ThreadLocalORMSession.close_all()

