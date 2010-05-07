from itertools import chain

from formencode import schema as fes
from formencode.foreach import ForEach
from formencode import validators as fev

from .validators import TimeConverter, DateConverter
from .core import Widget, WidgetInstance

class InputField(Widget):
    template = 'ew.templates.input_field'
    params=['name', 'value', 'label', 'attrs', 'readonly',
            'show_label', 'show_errors', 'field_type',
            'css_class']
    name=None
    value=None
    label=None
    show_label=True
    show_errors=True
    field_type=None
    css_class=None
    readonly=False
    attrs = {}
    validator = fev.UnicodeString()
    perform_validation = True

    def __init__(self, **kw):
        self._if_missing = ()
        super(InputField, self).__init__(**kw)
        if self.label is None and self.name:
            self.label = self.name.capitalize()

    def _get_if_missing(self):
        if self._if_missing == ():
            return self.validator.if_missing
        else:
            return self._if_missing
    def _set_if_missing(self, value):
        self._if_missing = value
    if_missing = property(_get_if_missing, _set_if_missing)

    def to_python(self, value, state=None):
        if self.validator:
            return self.validator.to_python(value, state)
        else:
            return value

    def from_python(self, value, state=None):
        if self.validator:
            try:
                return self.validator.from_python(value, state)
            except:
                return value
        else:
            return value

class HiddenField(InputField):
    show_label=False
    show_errors=False
    field_type='hidden'

class CompoundField(InputField):
    params = ['fields', 'hidden_fields', 'extra_fields']
    template = 'ew.templates.compound_field'
    fields=[]
    hidden_fields = []
    extra_fields = []
    chained_validators = []

    def to_python(self, value, state=None):
        schema = self._make_schema()
        result =  schema.to_python(value, state)
        return result

    def from_python(self, value, state=None):
        try:
            if not isinstance(value, dict):
                value = dict((k, getattr(value, k)) for k in dir(value))
            result = self._make_schema().from_python(value, state)
            d = dict(value)
            d.update(result)
            return d
        except:
            return value

    def _all_fields(self):
        return chain(self.fields, self.hidden_fields, self.extra_fields)

    def _make_schema(self):
        kwargs = dict((f.name, f) for f in self._all_fields()
                      if f.name and f.perform_validation)
        for f in self.fields:
            if f.name: continue
            if hasattr(f, '_make_schema'):
                kwargs.update(f._make_schema().fields)
        kwargs.update(chained_validators=self.chained_validators,
                      allow_extra_fields=True,
                      filter_extra_fields=True)
        return fes.Schema(**kwargs)

    def resources(self):
        for f in chain(self.fields, self.hidden_fields, self.extra_fields):
            for r in f.resources(): yield r

    def subwidget(self, parent, w, context):
        return WidgetInstance(w, context, parent=parent)

class RowField(CompoundField):
    template = 'ew.templates.row_field'

class FieldSet(CompoundField):
    template = 'ew.templates.field_set'
    show_label=False

class RepeatedField(InputField):
    template = 'ew.templates.repeated_field'
    params = ['field', 'repetitions']
    chained_validators = []
    field=None
    repetitions=3
    fields = hidden_fields = []

    def __init__(self, **kw):
        self._name = None
        if kw.get('field', self.field) is None:
            fields = kw.get('fields', self.fields)
            hidden_fields = kw.get('hidden_fields', self.hidden_fields)
            kw['field'] = CompoundField(fields=fields, hidden_fields=hidden_fields)
        super(RepeatedField, self).__init__(**kw)

    def __call__(self, **kw):
        context = dict(
            (k, getattr(self, k))
            for k in self.params)
        context.update(kw, widget=self)
        value = context.get('value')
        if value is not None:
            context['repetitions'] = len(value)
        return context

    def _get_name(self):
        if self._name is None:
            return self.field.name
        return self._name
    def _set_name(self, value):
        self._name = value
    name = property(_get_name, _set_name)

    def to_python(self, value, state=None):
        return self._make_schema().to_python(value, state)

    def from_python(self, value, state=None):
        if value is None: return None
        return self._make_schema().from_python(value, state)

    def _make_schema(self):
        return ForEach(self.field, if_missing=[], if_empty=[])

    def resources(self):
        return self.field.resources()

    def subwidget(self, parent, index, context):
        return WidgetInstance(self.field, context, parent=parent)

class TableField(RepeatedField):
    template = 'ew.templates.table_field'
    show_label = False

    def __init__(self, **kw):
        if kw.get('field', self.field) is None:
            fields = kw.get('fields', self.fields)
            hidden_fields = kw.get('hidden_fields', self.hidden_fields)
            kw['field'] = RowField(fields=fields, hidden_fields=hidden_fields)
        super(TableField, self).__init__(**kw)

class TextField(InputField):
    validator = fev.UnicodeString()
    field_type='text'

    def __init__(self, **kw):
        super(TextField, self).__init__(**kw)
        if self.label is None:
            self.label = self.name

class EmailField(TextField):
    validator = fev.Email()

class NumberField(TextField):
    validator = fev.Number()

class IntField(TextField):
    validator = fev.Int()

class DateField(TextField):
    validator=DateConverter()
    attrs = {'style':'width:6em'}

class TimeField(TextField):
    validator=TimeConverter()
    attrs = {'style':'width:5em'}

    def __init__(self, *args, **kwargs):
        self.validator = TimeConverter(use_seconds=False)
        TextField.__init__(self, *args, **kwargs)

class TextArea(InputField):
    template = 'ew.templates.text_area'
    validator = fev.UnicodeString()
    params=['css_class', 'cols']
    css_class = None
    cols = 60

    def __init__(self, **kw):
        super(TextArea, self).__init__(**kw)
        if self.label is None:
            self.label = self.name

    def to_python(self, value, state=None):
        if self.validator:
            return self.validator.to_python(value, state)
        else:
            return value

    def from_python(self, value, state=None):
        if self.validator:
            return self.validator.from_python(value, state)
        else:
            return value

class Checkbox(InputField):
    template='ew.templates.checkbox'
    show_label=False
    validator=fev.StringBool(if_empty=False, if_missing=False)
    params=['suppress_label']
    suppress_label=False

class SubmitButton(InputField):
    template='ew.templates.submit_field'
    show_label=False
    validator=fev.UnicodeString(if_empty=None, if_missing=None)
    field_type='submit'
    css_class='submit'

class LinkField(Widget):
    template='ew.templates.link'
    params=['name', 'href', 'attrs', 'label', 'text', 'show_label']
    label = None
    name=None
    href=None
    attrs=None
    text=None
    show_label=False

class HTMLField(Widget): # InputField):
    template='ew.templates.html_field'
    show_label=False
    params=['text', 'name']
    text=''
    name=None
    perform_validation = False
