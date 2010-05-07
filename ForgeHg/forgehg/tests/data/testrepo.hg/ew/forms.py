from itertools import chain

from formencode import schema as fes
from pylons.i18n import lazy_ugettext as l_

from .fields import CompoundField, SubmitButton

class SimpleForm(CompoundField):
    template = 'ew.templates.simple_form'
    params = [ 'method', 'action', 'submit_text', 'buttons', 'enctype', 'attrs' ]
    suppress_parent_params=['method', 'action', 'submit_text', 'buttons', 'enctype', 'attrs']
    method='POST'
    action=None
    submit_text='Submit'
    enctype=None
    show_label=False
    attrs=None
    buttons=[]
    button_class = SubmitButton

    def __init__(self, **kw):
        kw.setdefault('extra_fields', [])
        kw.setdefault('buttons', self.buttons)
        super(SimpleForm, self).__init__(**kw)

    def _all_fields(self):
        return chain(super(SimpleForm, self)._all_fields(), self.buttons)

    def _make_schema(self):
        base_schema = super(SimpleForm, self)._make_schema()
        if self.name:
            return fes.Schema(**{self.name:base_schema,
                             'allow_extra_fields':True,
                             'filter_extra_fields':True})
        else:
            return base_schema

    def __call__(self, **kw):
        result = super(SimpleForm, self).__call__(**kw)
        if result['submit_text'] is not None:
            b = self.button_class(label=l_(result['submit_text']))
            result['buttons'] = [b] + result['buttons']
        result['extra_fields'] += result['buttons']
        return result
