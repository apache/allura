'''TG compatibility shim
'''
import types
import urllib

import pkg_resources
import pyramid.response
from webob import exc

from decorators import Decoration

from . import tg_globals

__all__ = [ 'redirect', 'url' ]

class RootFactory(object):

    def __init__(self, root):
        self._ep = pkg_resources.EntryPoint.parse('root=' + root)
        self._root = None

    @property
    def root_class(self):
        if self._root is None:
            self._root = self._ep.load(require=False)
        return self._root

    def __call__(self, request):
        registry = request.environ['paste.registry']
        registry.register(tg_globals.request, request)
        registry.register(tg_globals.session, request.session)
        registry.register(tg_globals.response, pyramid.response.Response())
        root_obj = self.root_class()
        if hasattr(root_obj, '_setup_request'):
            root_obj._setup_request()
        try:
            response = Resource(root_obj)
            return response
        finally:
            if hasattr(root_obj, '_cleanup_request'):
                root_obj._cleanup_request()

class Resource(object):

    def __init__(self, controller):
        self._controller = controller

    def __getitem__(self, name):
        try:
            remainder = []
            if name.startswith('_'):
                next, remainder = self._controller._lookup(name)
            else:
                next = getattr(self._controller, name, None)
                if next is None:
                    next, remainder = self._controller._lookup(name)
            assert not remainder, 'Weird _lookup not supported'
            return Resource(next)
        except exc.HTTPNotFound:
            return None

    def get_deco(self):
        func = self._controller
        deco = Decoration.get(func, False)
        if deco is None:
            func = getattr(func, 'index', None)
            deco = Decoration.get(func, False)
        return deco, func

def tg_view(context, request):
    deco, func = context.get_deco()
    try:
        if not deco or not deco.exposed: raise exc.HTTPNotFound()
        deco.execute_controller(func, request)
    except exc.WSGIHTTPException, err:
        registry = request.environ['paste.registry']
        registry.register(tg_globals.response, err)
    return tg_globals.response

def redirect(location, *args, **kwargs):
    raise exc.HTTPFound(location=location)
    assert False

def smart_str(s, encoding='utf-8', strings_only=False, errors='strict'):
    """
    Returns a bytestring version of 's', encoded as specified in 'encoding'.

    If strings_only is True, don't convert (some) non-string-like objects.

    This function was borrowed from Django
    """
    if strings_only and isinstance(s, (types.NoneType, int)):
        return s
    elif not isinstance(s, basestring):
        try:
            return str(s)
        except UnicodeEncodeError:
            if isinstance(s, Exception):
                # An Exception subclass containing non-ASCII data that doesn't
                # know how to print itself properly. We shouldn't raise a
                # further exception.
                return ' '.join([smart_str(arg, encoding, strings_only,
                        errors) for arg in s])
            return unicode(s).encode(encoding, errors)
    elif isinstance(s, unicode):
        r = s.encode(encoding, errors)
        return r
    elif s and encoding != 'utf-8':
        return s.decode('utf-8', errors).encode(encoding, errors)
    else:
        return s

def generate_smart_str(params):
    for key, value in params.iteritems():
        if value is None: continue
        if isinstance(value, (list, tuple)):
            for item in value:
                yield smart_str(key), smart_str(item)
        else:
            yield smart_str(key), smart_str(value)

def urlencode(params):
    """
    A version of Python's urllib.urlencode() function that can operate on
    unicode strings. The parameters are first case to UTF-8 encoded strings and
    then encoded as per normal.
    """
    return urllib.urlencode([i for i in generate_smart_str(params)])

def url(base_url, params=None):
    if params is None: params = {}
    if params:
        return '?'.join((base_url, urlencode(params)))
    else:
        return base_url
