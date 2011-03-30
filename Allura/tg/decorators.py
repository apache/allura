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

def override_template(func, template):
    c.override_template = template

def without_trailing_slash(func):
    from tg import redirect
    def _check_path(params):
        if request.method != 'GET': return
        if request.path.endswith('/'):
            redirect(request.url.replace(request.path, request.path[:-1], 1))
    before_validate(_check_path)(func)
    return func

def with_trailing_slash(func):
    from tg import redirect
    def _check_path(params):
        if request.method != 'GET': return
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
        assert not self._templates, 'Multiple @expose not supported in shim'
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
            if hasattr(self._validators, 'to_python'):
                params = self._validators.to_python(params, state)
            elif hasattr(self._validators, 'validate'):
                params = self._validators.validate(params, state)
            else:
                assert False, 'unknown validator type: %r' % self._validators
        return params

    def do_render_response(self, result):
        tname = self._lookup_template()
        if tname in ('json', 'json:'):
            engine, tname = 'json', 'json'
            response.content_type = 'application/json'
        elif tname is None:
            return self._make_iter(result)
        else:
            engine, tname = tname.split(':', 1)
        f = ew.render.File(tname, engine)
        return self._make_iter(f(result))

    def _lookup_template(self):
        tpl = getattr(c, 'override_template', None)
        if tpl is not None: return tpl
        if len(self._templates) > 1:
            assert False, 'Multiple @expose not supported in shim'
        if not self._templates: return None
        ct, tname = self._templates.items()[0]
        if ct is not None:
            response.content_type = ct
        return tname

    def _make_iter(self, result):
        if isinstance(result, unicode):
            return [ result.encode('utf-8') ]
        elif isinstance(result, str):
            return [ result ]
        else:
            return result
