from tg import expose
from webob import exc

class BaseController(object):
    @expose()
    def _lookup(self, name, *remainder):
        """Provide explicit default lookup to avoid dispatching backtracking
        and possible loops."""
        raise exc.HTTPNotFound, name