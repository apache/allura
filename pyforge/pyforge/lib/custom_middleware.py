import logging
from contextlib import contextmanager
from threading import local

import pylons
from webob import exc, Request

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
            pylons.c._pop_object(magical_c)

    def _cleanup_request(self, environ):
        carrot = environ.pop('allura.carrot.connection', None)
        if carrot: carrot.close()
        _environ.set_environment({})

    def _cleanup_iterator(self, result, environ):
        for x in result:
            yield x
        self._cleanup_request(environ)

class SfxLoginMiddleware(object):

    def __init__(self, app, config):
        from sf.phpsession import SFXSessionMgr
        self.app = app
        self.config = config
        self.sfx_session_mgr = SFXSessionMgr()
        self.sfx_session_mgr.setup_sessiondb_connection_pool(config)

    def __call__(self, environ, start_response):
        request = Request(environ)
        try:
            self.handle(request)
        except exc.HTTPException, resp:
            return resp(environ, start_response)
        resp = request.get_response(self.app)
        return resp(environ, start_response)

    def handle(self, request):
        from pyforge import model as M
        session = request.environ['beaker.session']
        cookie_name = self.sfx_session_mgr.cookie_name
        mgr = self.sfx_session_mgr
        if 'userid' in session:
            if cookie_name not in request.cookies:
                # user should be logged out
                session.clear()
                session.save()
                # don't redirect or show message though, since they might've logged out of sf.net days ago
                # and just now returned to this app
                return
            elif request.cookies[cookie_name] == session.get('sfx-sessid'):
                # already logged in
                return

        sfx_user_id = mgr.userid_from_session_cookie(request.cookies)
        if sfx_user_id:
            server_name = request.environ['HTTP_HOST']
            user_data = mgr.user_data(server_name, sfx_user_id)
            user = M.User.query.get(username=user_data['username'])
            if not user:
                with fake_pylons_context(request):
                    user = M.User(username=user_data['username'],
                                  display_name=user_data['name'])
                    n = M.Neighborhood.query.get(name='Users')
                    n.register_project('u/' + user.username, user, user_project=True)
            if user.display_name != user_data['name']:
                user.display_name = user_data['name']
            sfx_user_id_num = int(sfx_user_id.split(':')[-1])
            if user.sfx_userid != sfx_user_id_num:
                user.sfx_userid = sfx_user_id_num
            session['sfx-sessid'] = request.cookies[cookie_name]
            session['userid'] = user._id
            session.save()

class SSLMiddleware(object):
    'Verify the https/http schema is correct'

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        req = Request(environ)
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
    from pyforge.lib.app_globals import Globals
    class EmptyClass(object): pass
    pylons.c._push_object(MagicalC(EmptyClass(), environ))
    pylons.g._push_object(Globals())
    pylons.request._push_object(request)
    yield
    pylons.c._pop_object()
    pylons.g._pop_object()
    pylons.request._pop_object()

on_import()
