from formencode import Invalid
from webob import exc

from . import tg_globals
from .decorators import Decoration

def tg_view(context, request):
    deco, func = context.get_deco()
    try:
        if not deco or not deco.exposed: raise exc.HTTPNotFound()
        try:
            # Validate params
            params = deco.do_validate_params(request.params.mixed())
            result = func(**params)
        except Invalid, inv:
            tg_globals.c.validation_exception = inv
            eh = deco.error_handler
            if eh:
                result = eh(func.im_self, **request.params)
                deco = Decoration.get(deco.error_handler, False)
            else:
                result = func(**request.params)
        tg_globals.response.app_iter = deco.do_render_response(result)
    except exc.WSGIHTTPException, err:
        registry = request.environ['paste.registry']
        response = request.get_response(err)
        registry.register(tg_globals.response, response)
    return tg_globals.response

def error_view(context, request):
    return context
