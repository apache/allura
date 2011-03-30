import types
import urllib

from webob import exc

from .tg_globals import request

def call_wsgi_application(application, environ, catch_exc_info=False):
    """
    Call the given WSGI application, returning ``(status_string,
    headerlist, app_iter)``

    Be sure to call ``app_iter.close()`` if it's there.

    If catch_exc_info is true, then returns ``(status_string,
    headerlist, app_iter, exc_info)``, where the fourth item may
    be None, but won't be if there was an exception.  If you don't
    do this and there was an exception, the exception will be
    raised directly.
    """
    captured = []
    output = []
    def start_response(status, headers, exc_info=None):
        if exc_info is not None and not catch_exc_info:
            raise exc_info[0], exc_info[1], exc_info[2]
        captured[:] = [status, headers, exc_info]
        return output.append
    app_iter = application(environ, start_response)
    if not captured or output:
        try:
            output.extend(app_iter)
        finally:
            if hasattr(app_iter, 'close'):
                app_iter.close()
        app_iter = output
    if catch_exc_info:
        return (captured[0], captured[1], app_iter, captured[2])
    else:
        return (captured[0], captured[1], app_iter)


def redirect(*args, **kwargs):
    found = exc.HTTPFound(location=url(*args, **kwargs))
    raise found.exception

def moved(*args, **kwargs):
    moved = exc.HTTPMovedPermanently(location=url(*args, **kwargs))
    raise moved.exception

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

def url(base_url=None, params=None):
    if base_url is None: base_url = '/'
    if params is None: params = {}
    if hasattr(base_url, '__iter__' ) and not isinstance(base_url, basestring):
        base_url = '/'.join(base_url)
    if base_url.startswith('/'):
        base_url = request.environ['SCRIPT_NAME'] + base_url
    if params:
        return '?'.join((base_url, urlencode(params)))
    return base_url
