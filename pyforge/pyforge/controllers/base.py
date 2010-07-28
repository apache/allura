from tg import expose
from webob import exc

class BaseController(object):
    @expose()
    def _lookup(self, name, *remainder):
        raise exc.HTTPNotFound, name