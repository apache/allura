import os
import re
import logging
from contextlib import contextmanager
from threading import local
from random import random

import tg
import pylons
import pkg_resources
import markdown
from paste import fileapp
from paste.deploy.converters import asbool
from pylons.util import call_wsgi_application
from tg.controllers import DecoratedController
from webob import exc, Request

from allura.lib.stats import timing, StatsRecord

log = logging.getLogger(__name__)

environ = _environ = None

def on_import():
    global environ, _environ
    environ = _environ = Environ()

class ForgeMiddleware(object):
    '''Middleware responsible for pushing the MagicalC object and setting the
    threadlocal _environ.  This is inner middleware, and must be called from
    within the TGController.__call__ method because it depends on pylons.c and pylons.g'''

    def __init__(self, app):
        self.app = app
        self.g = pylons.g._current_obj()

    def __call__(self, environ, start_response):
        _environ.set_environment(environ)
        magical_c = MagicalC(pylons.c._current_obj(), environ)
        pylons.c._push_object(magical_c)
        try:
            result = self.app(environ, start_response)
            if isinstance(result, list):
                self._cleanup_request(environ)
                return result
            else:
                return self._cleanup_iterator(result, environ)
        finally:
            pylons.c._pop_object()

    def _cleanup_request(self, environ):
        for msg in environ.get('allura.queued_messages', []):
            self.g._publish(**msg)
        carrot = environ.pop('allura.carrot.connection', None)
        if carrot: carrot.close()
        _environ.set_environment({})

    def _cleanup_iterator(self, result, environ):
        for x in result:
            yield x
        self._cleanup_request(environ)

class StaticFilesMiddleware(object):
    '''Custom static file middleware

    Map everything in allura/public/nf/* to <script_name>/*
    For each plugin, map everything <module>/nf/<ep_name>/* to <script_name>/<ep_name>/*
    '''
    CACHE_MAX_AGE=60*60*24*365

    def __init__(self, app, script_name=''):
        self.app = app
        self.script_name = script_name
        self.directories = [
            (self.script_name + ep.name + '/', ep)
            for ep in pkg_resources.iter_entry_points('allura') ]

    def __call__(self, environ, start_response):
        environ['static.script_name'] = self.script_name
        if not environ['PATH_INFO'].startswith(self.script_name):
            return self.app(environ, start_response)
        try:
            app = self.get_app(environ)
            app.cache_control(public=True, max_age=self.CACHE_MAX_AGE)
            return app(environ, start_response)
        except OSError:
            return exc.HTTPNotFound()(environ, start_response)

    def get_app(self, environ):
        for prefix, ep in self.directories:
            if environ['PATH_INFO'].startswith(prefix):
                filename = environ['PATH_INFO'][len(prefix):]
                file_path = pkg_resources.resource_filename(
                    ep.module_name, os.path.join(
                        'nf',
                        ep.name,
                        filename))
                return fileapp.FileApp(file_path, [
                        ('Access-Control-Allow-Origin', '*')])
        filename = environ['PATH_INFO'][len(self.script_name):]
        file_path = pkg_resources.resource_filename(
            'allura', os.path.join(
                'public', 'nf',
                filename))
        return fileapp.FileApp(file_path, [
                ('Access-Control-Allow-Origin', '*')])

class LoginRedirectMiddleware(object):
    '''Actually converts a 401 into a 302 so we can do a redirect to a different
    app for login.  (StatusCodeRedirect does a WSGI-only redirect which cannot
    go to a URL not managed by the WSGI stack).'''

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        status, headers, app_iter, exc_info = call_wsgi_application(
            self.app, environ, catch_exc_info=True)
        if status[:3] == '401':
            login_url = tg.config.get('auth.login_url', '/auth/')
            location = tg.url(login_url, dict(return_to=environ['PATH_INFO']))
            r = exc.HTTPFound(location=location)
            return r(environ, start_response)
        start_response(status, headers, exc_info)
        return app_iter

class CSRFMiddleware(object):
    '''On POSTs, looks for a special field name that matches the value of a given
    cookie.  If this field is missing, the cookies are cleared to anonymize the
    request.'''

    def __init__(self, app, cookie_name, param_name=None):
        if param_name is None: param_name = cookie_name
        self._app = app
        self._param_name = param_name
        self._cookie_name = cookie_name

    def __call__(self, environ, start_response):
        req = Request(environ)
        param = req.str_POST.pop(self._param_name, None)
        if req.method == 'POST':
            cookie = req.cookies.get(self._cookie_name)
            if cookie != param:
                log.warning('CSRF attempt detected, %r != %r', cookie, param)
                del environ['HTTP_COOKIE']
        return self._app(environ, start_response)


class SSLMiddleware(object):
    'Verify the https/http schema is correct'

    def __init__(self, app, no_redirect_pattern=None):
        self.app = app
        if no_redirect_pattern:
            self._no_redirect_re = re.compile(no_redirect_pattern)
        else:
            self._no_redirect_re = re.compile('$$$')

    def __call__(self, environ, start_response):
        req = Request(environ)
        if self._no_redirect_re.match(environ['PATH_INFO']):
            return req.get_response(self.app)(environ, start_response)
        resp = None
        try:
            request_uri = req.url
            request_uri.decode('ascii')
        except UnicodeError:
            resp = exc.HTTPNotFound()
        secure = req.environ.get('HTTP_X_SFINC_SSL', 'false') == 'true'
        srv_path = req.path_url.split('://', 1)[-1]
        if req.cookies.get('SFUSER'):
            if not secure:
                resp = exc.HTTPFound(location='https://' + srv_path)
        elif secure:
            resp = exc.HTTPFound(location='http://' + srv_path)

        if resp is None:
            resp = req.get_response(self.app)
        return resp(environ, start_response)

class StatsMiddleware(object):

    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.log = logging.getLogger('stats')
        self.active = False
        try:
            self.sample_rate = config.get('stats.sample_rate', 0.25)
            self.debug = asbool(config.get('debug', 'false'))
            self.instrument_pymongo()
            self.instrument_template()
            self.active = True
        except KeyError:
            self.sample_rate = 0

    def instrument_pymongo(self):
        import pymongo.collection
        import ming.orm
        timing('mongo').decorate(pymongo.collection.Collection,
                                 'count find find_one')
        timing('mongo').decorate(pymongo.cursor.Cursor,
                                 'count distinct explain hint limit next rewind'
                                 ' skip sort where')
        timing('ming').decorate(ming.orm.ormsession.ORMSession,
                                'flush find get')
        timing('ming').decorate(ming.orm.ormsession.ORMCursor,
                                'next')

    def instrument_template(self):
        import jinja2
        import genshi.template
        timing('template').decorate(genshi.template.Template,
                                    '_prepare _parse generate')
        timing('render').decorate(genshi.Stream,
                                  'render')
        timing('render').decorate(jinja2.Template,
                                  'render')
        timing('markdown').decorate(markdown.Markdown,
                                    'convert')


    def __call__(self, environ, start_response):
        req = Request(environ)
        req.environ['sf.stats'] = s = StatsRecord(req, random() < self.sample_rate)
        with s.timing('total'):
            resp = req.get_response(self.app, catch_exc_info=self.debug)
            result = resp(environ, start_response)
        if s.active:
            self.log.info('Stats: %r', s)
            from allura import model as M
            M.Stats.make(s.asdict()).m.insert()
        return result

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

    def __contains__(self, key):
        return self._local.environ and key in self._local.environ

class MagicalC(object):
    '''Magically saves various attributes to the environ'''
    _saved_attrs = set(['project', 'app', 'queued_messages'])

    def __init__(self, old_c, environ):
        self._old_c = old_c
        self._environ = environ

    def __getattr__(self, name):
        return getattr(self._old_c, name)

    def __setattr__(self, name, value):
        if name in MagicalC._saved_attrs:
            self._environ['allura.' + name] = value
        if name not in ('_old_c', '_environ'):
            setattr(self._old_c, name, value)
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if name not in ('_old_c', '_environ'):
            delattr(self._old_c, name)
        object.__delattr__(self, name)

@contextmanager
def fake_pylons_context(request):
    from allura.lib.app_globals import Globals
    class EmptyClass(object): pass
    pylons.c._push_object(MagicalC(EmptyClass(), environ))
    pylons.g._push_object(Globals())
    pylons.request._push_object(request)
    try:
        yield
    finally:
        pylons.c._pop_object()
        pylons.g._pop_object()
        pylons.request._pop_object()

on_import()
