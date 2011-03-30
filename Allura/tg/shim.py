'''TG compatibility shim
'''
import pkg_resources
import pyramid.response

from . import tg_globals
from .traversal import Resource

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

