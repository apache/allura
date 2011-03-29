from formencode import Invalid, schema

import ew.render

from .tg_globals import c, response

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
    return func

def with_trailing_slash(func):
    return func

class Decoration(object):
    attrname = 'tg_decoration'

    def __init__(self, func):
        setattr(func, self.attrname, self)
        self.exposed = False
        self._templates = {}
        self._validators = None
        self._error_handler = None
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

    def validate(self, validators, error_handler=None):
        if isinstance(validators, dict):
            validators = schema.Schema(
                fields=validators,
                allow_extra_fields=True)
        self._validators = validators
        self._error_handler = error_handler

    def before_validate(self, func):
        self._before_validate.append(func)

    def execute_controller(self, func, request):
        try:
            # Validatate parameters
            params = dict(request.params)
            for hook in self._before_validate:
                hook(params)
            if self._validators:
                params = self._validators.to_python(params, None)
            # Execute controller
            result = func(**params)
        except Invalid, inv:
            c.validation_exception = inv
            params = dict(request.params)
            if self._error_handler:
                result = self._error_handler(**params)
            else:
                result = func(**params)
        # render response
        if len(self._templates) == 1:
            ct, tname = self._templates.items()[0]
            if ct is not None:
                response.content_type = ct
            if tname == 'json':
                engine, tname = 'json', 'json'
            else:
                engine, tname = tname.split(':', 1)
            f = ew.render.File(tname, engine)
            rendered_result = f(result)
        elif self._templates:
            assert False, 'Multiple @expose not supported in shim'
        else:
            rendered_result = result
        response.app_iter = rendered_result
