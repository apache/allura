from formencode import validators as fev
from formencode import compound as fec
from formencode.foreach import ForEach

from .core import Widget
from .fields import InputField
from .validators import OneOf

class SelectField(InputField):
    params=['options']
    validator=fev.UnicodeString()
    _options = []

    def __init__(self, **kwargs):
        self._options = kwargs.pop('options', self._options)
        super(SelectField, self).__init__(**kwargs)

    def to_python(self, value, state=None):
        schema = self._make_schema()
        result = schema.to_python(value, state)
        return result

    def from_python(self, value, state=None):
        return self._make_schema().from_python(value, state)

    def _get_options(self):
        if callable(self._options):
            return self._options()
        else:
            return self._options
    def _set_options(self, value):
        self._options = value
    options = property(_get_options, _set_options)

    def option_object_for(self, value, option):
        if not isinstance(option, Option):
            option = Option(label=unicode(option), py_value=unicode(option))
        if option.html_value is None:
            option.html_value = self.validator.from_python(option.py_value, None)
        return option

class SingleSelectField(SelectField):
    template='ew.templates.single_select_field'

    def option_object_for(self, value, option):
        option = super(SingleSelectField, self).option_object_for(value, option)
        if option.html_value == value or (value is None and option.selected):
            option.selected = True
        else:
            option.selected = False
        return option

    def _make_schema(self):
        oneof_validator = OneOf(
            lambda:[self.option_object_for((), o).html_value
                    for o in self.options ])
        return fec.All(
            self.validator,
            oneof_validator)

class MultiSelectField(SelectField):
    template='ew.templates.multi_select_field'

    def __init__(self, **kw):
        super(MultiSelectField, self).__init__(**kw)
        self.if_missing  = []

    def option_object_for(self, value, option):
        option = super(MultiSelectField, self).option_object_for(value, option)
        if option.html_value in value:
            option.selected = True
        else:
            option.selected = False
        return option

    def _make_schema(self):
        validator = fec.All(
            self.validator,
            OneOf(
                lambda:[self.option_object_for((), o).html_value
                        for o in self.options ]))
        return ForEach(validator, convert_to_list=True, if_empty=[], if_missing=[])

    # def from_python(self, value, state):
    #     return [ self.validator.from_python(v, state)
    #              for v in value ]


class CheckboxSet(MultiSelectField):
    template = 'ew.templates.checkbox_set'
    params=['option_widget']
    show_label=False
    option_widget=None

class Option(Widget):
    template = 'ew.templates.option'
    params = [ 'html_value', 'py_value', 'label', 'selected' ]
    html_value = None
    py_value = None
    label = None
    selected = False
