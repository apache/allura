import cgi
import urllib

def parse_uri(uri, **kwargs):
    scheme, rest = urllib.splittype(uri)
    host, rest = urllib.splithost(rest)
    user, rest = urllib.splituser(rest)
    if user:
        username, password = urllib.splitpasswd(user)
    else:
        username = password = None
    host, port = urllib.splitnport(host)
    path, query = urllib.splitquery(rest)
    if query:
        kwargs.update(dict(cgi.parse_qsl(query)))
    return dict(
        scheme=scheme,
        host=host,
        username=username,
        password=password,
        port=port,
        path=path,
        query=kwargs)

class LazyProperty(object):

    def __init__(self, func):
        self._func = func
        self.__name__ = func.__name__
        self.__doc__ = func.__doc__

    def __get__(self, obj, klass=None):
        if obj is None: return None
        result = obj.__dict__[self.__name__] = self._func(obj)
        return result

