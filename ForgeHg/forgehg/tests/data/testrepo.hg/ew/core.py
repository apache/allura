from __future__ import with_statement
import logging
import string
from contextlib import contextmanager

import tg
from tg.render import render as tg_render
from tg import expose
import pylons
from pylons import c
from formencode import validators as fev
from formencode import schema as fes

try:
    from tg.decorators import variable_decode
except ImportError: # pragma no cover
    from tg.decorators import before_validate
    from formencode import variabledecode

    @before_validate
    def variable_decode(remainder, params):
        '''Best-effort formencode.variabledecode on the params before validation

        If any exceptions are raised due to invalid parameter names, they are
        silently ignored, hopefully to be caught by the actual validator.  Note that
        this decorator will *add* parameters to the method, not remove.  So for
        instnace a method will move from {'foo-1':'1', 'foo-2':'2'} to
        {'foo-1':'1', 'foo-2':'2', 'foo':['1', '2']}.
        '''
        try:
            new_params = variabledecode.variable_decode(params)
            params.update(new_params)
        except:
            pass

log = logging.getLogger(__name__)

class ExprTemplate(string.Template):
    idpattern = r'[_a-z][^}]*'

class Widget(fev.Validator):
    _id = 0
    # Params are copied to the template context from the widget
    params=[]
    perform_validation = False
    template=None
    exclude_names=[]
    content_type='text/html'

    class __metaclass__(fev.Validator.__metaclass__):
        '''Make sure that the params lists of base classes are additive'''
        def __new__(meta, name, bases, dct):
            params = []
            for b in bases:
                params += getattr(b, 'params', [])
            dct['params'] = params + dct.get('params', [])
            return type.__new__(meta, name, bases, dct)

    def __init__(self, **kw):
        params = kw.pop('params', [])
        self.params = self.__class__.params + params
        self._id = Widget._id
        Widget._id += 1
        for k,v in kw.iteritems():
            setattr(self, k, v)
        if self.template:
            expose(self.template)(self)

    def __call__(self, **context):
        response = dict(
            (k, getattr(self, k))
            for k in self.params)
        response.update(context)
        return response

    def validate(self, value, state):
        return self.to_python(value, state)

    def display(self, **kw):
        wi = WidgetInstance(self, dict(kw), parent=(getattr(c, 'widget', None) or None))
        return wi.display()

    def resources(self):
        return []

class ControllerWidget(Widget):
    def __init__(self, controller):
        self.controller = controller
        if controller.decoration.validation:
            self.validator = controller.decoration.validation.validators
        else:
            self.validator = None
        self.decoration = controller.decoration
        for content_type, (engine_name, template_name, exclude_names) \
                in self.decoration.engines.iteritems():
            if 'html' in content_type: break
        self.template = '%s:%s' % (engine_name, template_name)
        self.exclude_names = exclude_names
        self.content_type = content_type

    def __call__(self, **kw):
        response = self.controller(**kw)
        return response

    def to_python(self, value, state=None):
        s = self._make_schema()
        if s is None: return value
        return s.to_python(value, state)

    def from_python(self, value, state=None):
        try:
            s = self._make_schema()
            if s is None:
                return value
            if value is None:
                return None
            return s.from_python(value, state)
        except fev.Invalid, inv: # pragma no cover
            return value

    def _make_schema(self):
        if not isinstance(self.validator, dict):
            return self.validator
        kwargs = dict(self.validator)
        kwargs.update(allow_extra_fields=True,
                      filter_extra_fields=True)
        return fes.Schema(**kwargs)

class WidgetInstance(object):

    def __init__(self, widget_type, context=None, parent=None):
        if context is None: context = {}
        self.widget_type = widget_type
        self.context = context
        self.response = None
        self.parent = parent

    def __repr__(self):
        return 'I-%r' % self.widget_type

    def _override_context(self):
        if self.parent: return
        widget_name = self.context.get('name', getattr(self.widget_type, 'name', None))
        if not hasattr(c, 'validation_exception'): return
        try:
            if c.validation_exception.value:
                value =  c.validation_exception.value
                errors = c.validation_exception.unpack_errors()
                if widget_name:
                    if widget_name not in errors: return
                    errors = errors[widget_name]
                    value = value.get(widget_name, None)
                self.context.update(value=value, errors=errors)
        except:
            return

    def display(self):
        # Run the widget on the context
        self._override_context()
        response = self.widget_type(**self.context)
        # Update the results
        if self.parent:
            # Underlay parent response fields
            d = dict(self.parent.response)
            d.update(response)
            response = d
        self.response = response
        # Render the response
        with _push_context(c, widget=self):
            try:
                response = self._render_response(response)
            except Exception, ex:
                log.exception('Error rendering %s', self.widget_type)
                raise
        return response

    def subwidget(self, id, context):
        return self.widget_type.subwidget(self, id, context)

    def expand(self, tpl):
        '''Peform basic string.Template expansion in the current context'''
        tpl = ExprTemplate(unicode(tpl))
        context = ExprDict(self.response or self.context)
        return tpl.safe_substitute(context)

    def context_for(self, id=None):
        '''Return the context for the identified subwidget.  At a
        minimum, this will always return a dict with name, value, and errors
        present.
        '''
        if isinstance(id, basestring):
            result = self._context_for_str(id)
        elif isinstance(id, int):
            result = self._context_for_int(id)
        else:
            result = dict(self.context)
        result.setdefault('name', None)
        result.setdefault('value', None)
        result.setdefault('errors', None)
        return result

    def _context_for_str(self, name):
        result = dict(self.context)
        if self.response.get('name', None):
            result['name'] = self.response['name'] + '.' + name
        else:
            result['name'] = name
        result['value'] = _safe_getitem(result, 'value', name)
        result['errors'] = _safe_getitem(result, 'errors', name)
        return result

    def _context_for_int(self, index):
        result = dict(self.context)
        if self.response.get('name', None):
            result['name'] = '%s-%d' % (self.response['name'], index)
        result['value'] = _safe_getitem(result, 'value', index)
        result['errors'] = _safe_getitem(result, 'errors', index)
        return result

    def _render_response(self, response):
        if ':' in self.widget_type.template:
            engine_name, template_name = self.widget_type.template.split(':')
        else:
            config = pylons.configuration.config
            engine_name = pylons.configuration.config.get("default_renderer", 'genshi')
            template_name = self.widget_type.template
        exclude_names = self.widget_type.exclude_names
        if self.widget_type.content_type is not None:
            pylons.response.headers['Content-Type'] = self.widget_type.content_type

        # Save these objeccts as locals from the SOP to avoid expensive lookups
        req = pylons.request._current_obj()
        tmpl_context = pylons.tmpl_context._current_obj()

        #if there is an identity, push it to the pylons template context
        tmpl_context.identity = req.environ.get('repoze.who.identity')

        # Setup the template namespace, removing anything that the user
        # has marked to be excluded.
        namespace = dict(tmpl_context=tmpl_context)
        namespace.update(response)

        for name in exclude_names:
            namespace.pop(name)

        # If we are in a test request put the namespace where it can be
        # accessed directly
        if req.environ.get('paste.testing'):
            testing_variables = req.environ['paste.testing_variables']
            testing_variables['namespace'] = namespace
            testing_variables['template_name'] = template_name
            testing_variables['controller_output'] = response

        # Render the result.
        result = tg_render(template_vars=namespace,
                           template_engine=engine_name,
                           template_name=template_name)

        return result

class WidgetsList(list):
    '''Simple class to let you create a list of widgets declaratively'''
    class __metaclass__(type):
        def __new__(meta, name, bases, dct):
            if bases == (list,):
                return type.__new__(meta, name, bases, dct)
            result = NameList()
            result._index = dct
            for k,v in dct.iteritems():
                if isinstance(v, Widget):
                    if v.name is None:
                        v.name = k
                    if getattr(v, 'label', None) is None:
                        v.label = k.replace('_', ' ').title()
                    result.append(v)
            # Maintain declaration order
            result.sort(key=lambda w:w._id)
            return result

class NameList(list):

    def __getitem__(self, index):
        if isinstance(index, basestring):
            return self._index[index]
        return super(WidgetsList, self).__getitem__(index)


def _safe_getitem(dct, key, item):
    '''Return either dct[key][item],  dct[key].item, or None, whichever
    is appropriate
    '''
    if key not in dct: return None
    value = dct[key]
    try:
        result = value[item]
    except TypeError:
        if isinstance(item, str):
            result = getattr(value, item, None)
        else:
            result = None
    except (KeyError, IndexError), ex:
        result = None
    return result

@contextmanager
def _push_context(obj, **kw):
    '''Temporarily add attributes to 'obj', restoring 'obj' to its original
    state on __exit__
    '''
    new_keys = [ k for k in kw if not hasattr(obj, k) ]
    saved_items = [
        (k, getattr(obj, k)) for k in kw
        if hasattr(obj, k) ]
    for k,v in kw.iteritems():
        setattr(obj, k, v)
    yield obj
    for nk in new_keys:
        delattr(obj, nk)
    for k,v in saved_items:
        setattr(obj, k, v)

class ExprDict(dict):

    def get(self, k, *args):
        try:
            return self[k]
        except KeyError:
            if args: return args[0]
            raise

    def __getitem__(self, k):
        try:
            return eval(k, dict(self))
        except KeyError, ke:
            raise
        except Exception, ex:
            return '[Exception in %s: %s]' % (k, ex)


