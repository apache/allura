# -*- coding: utf-8 -*-

"""The base Controller API."""

from tg import TGController, tmpl_context, config
from tg.render import render
from pylons.i18n import _, ungettext, N_
from pylons import c, g
from tw.api import WidgetBunch
from paste.deploy.converters import asbool

import pkg_resources
from webob import exc
import ming
from threading import local

__all__ = ['BaseController']

class Environ(object):
    _local = local()

    def set_environment(self, environ):
        self._local.environ = environ

    def __getitem__(self, name):
        if not hasattr(self._local, 'environ'):
            self.set_environment({})
        try:
            return self._local.environ[name]
        except AttributeError:
            self._local.environ = {}
            raise KeyError, name

    def __setitem__(self, name, value):
        if not hasattr(self._local, 'environ'):
            self.set_environment({})
        try:
            self._local.environ[name] = value
        except AttributeError:
            self._local.environ = {name:value}

    def __delitem__(self, name):
        if not hasattr(self._local, 'environ'):
            self.set_environment({})
        try:
            del self._local.environ[name]
        except AttributeError:
            self._local.environ = {}
            raise KeyError, name

    def __getattr__(self, name):
        if not hasattr(self._local, 'environ'):
            self.set_environment({})
        return getattr(self._local.environ, name)

    def __repr__(self):
        if not hasattr(self._local, 'environ'):
            self.set_environment({})
        return repr(self._local.environ)

environ = _environ = Environ()

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
        _environ.set_environment(environ)

        if asbool(environ.get('HTTP_X_SFINC_SSL', 'false')):
            environ['wsgi.url_scheme'] = 'https'

        app = self._wsgi_handler(environ)
        if app is None:
            """Invoke the Controller"""
            # TGController.__call__ dispatches to the Controller method
            # the request is routed to. This routing information is
            # available in environ['pylons.routes_dict']
            app = lambda e,s: TGController.__call__(self, e, s)
        magical_c = MagicalC(c._current_obj())
        try:
            c._push_object(magical_c)
            self._setup_request()
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
        finally:
            c._pop_object(magical_c)

    def _wsgi_handler(self, environ):
        import pyforge.model as model
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

    def _setup_request(self):
        '''Responsible for setting all the values we need to be set on pylons.c'''
        raise NotImplementedError, '_setup_request'

    def _cleanup_request(self):
        ming.orm.ormsession.ThreadLocalORMSession.flush_all()
        ming.orm.ormsession.ThreadLocalORMSession.close_all()

class MagicalC(object):
    '''Magically saves various attributes to the environ'''
    _saved_attrs = set(['project', 'app', 'queued_messages'])

    def __init__(self, old_c):
        self._old_c = old_c

    def __getattr__(self, name):
        return getattr(self._old_c, name)

    def __setattr__(self, name, value):
        if name in MagicalC._saved_attrs:
            environ['allura.' + name] = value
        if name != '_old_c':
            setattr(self._old_c, name, value)
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if name != '_old_c':
            delattr(self._old_c, name)
        object.__delattr__(self, name)
