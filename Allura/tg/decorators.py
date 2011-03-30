from formencode import schema

import ew.render

from .tg_globals import c, request, response

class _tg_deco(object):
    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs
    def __call__(self, func):
        deco = Decoration.get(func, True)
        op = getattr(deco, self.__class__.__name__)
        op(*self.args, **self.kwargs)
        return func

class expose(_tg_deco): pass
class validate(_tg_deco): pass
class before_validate(_tg_deco): pass
class override_template(_tg_deco): pass

def without_trailing_slash(func):
    from tg import redirect
    def _check_path(params):
        if request.path.endswith('/'):
            redirect(request.url.replace(request.path, request.path[:-1], 1))
    before_validate(_check_path)(func)
    return func

def with_trailing_slash(func):
    from tg import redirect
    def _check_path(params):
        if not request.path.endswith('/'):
            redirect(request.url.replace(request.path, request.path + '/', 1))
    before_validate(_check_path)(func)
    return func

class Decoration(object):
    attrname = 'tg_decoration'

    def __init__(self, func):
        setattr(func, self.attrname, self)
        self.exposed = False
        self._templates = {}
        self._validators = None
        self.error_handler = None
        self._before_validate = []

    @classmethod
    def get(cls, func, create=False):
        r = getattr(func, cls.attrname, None)
        if r is None and create:
            return cls(func)
        return r

    def expose(self, template=None, content_type=None):
        self.exposed = True
        if template or content_type:
            self._templates[content_type] = template

    def validate(self, validators=None, error_handler=None, **kwargs):
        if validators is None:
            validators = kwargs.pop('form', None)
        if isinstance(validators, dict):
            validators = schema.Schema(
                fields=validators,
                if_key_missing=None,
                allow_extra_fields=True)
        self._validators = validators
        self.error_handler = error_handler

    def before_validate(self, func):
        self._before_validate.append(func)

    def do_validate_params(self, params):
        # An object used by FormEncode to get translator function
        for hook in self._before_validate:
            hook(params)
        if self._validators:
            state = type('state', (), {})
            params = self._validators.validate(params, state)
        return params

    def do_render_response(self, result):
        if len(self._templates) == 1:
            ct, tname = self._templates.items()[0]
            if ct is not None:
                response.content_type = ct
            if tname in ('json', 'json:'):
                engine, tname = 'json', 'json'
                response.content_type = 'application/json'
            else:
                engine, tname = tname.split(':', 1)
            f = ew.render.File(tname, engine)
            rendered_result = f(result)
        elif self._templates:
            assert False, 'Multiple @expose not supported in shim'
        else:
            rendered_result = result
        if isinstance(rendered_result, unicode):
            return [ rendered_result.encode('utf-8') ]
        elif isinstance(rendered_result, str):
            return [ rendered_result ]
        else:
            return rendered_result
