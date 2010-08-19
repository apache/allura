import webob
from tg.decorators import Decoration

from allura.lib import helpers as h


def apply():
    old_lookup_template_engine = Decoration.lookup_template_engine

    @h.monkeypatch(Decoration)
    def lookup_template_engine(self, request):
        '''Wrapper to handle totally borked-up HTTP-ACCEPT headers'''
        try:
            return old_lookup_template_engine(self, request)
        except:
            pass
        environ = dict(request.environ, HTTP_ACCEPT='*/*')
        request = webob.Request(environ)
        return old_lookup_template_engine(self, request)
