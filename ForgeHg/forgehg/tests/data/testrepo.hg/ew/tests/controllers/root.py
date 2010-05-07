# -*- coding: utf-8 -*-

import tg, pylons
from tg.controllers import TGController, CUSTOM_CONTENT_TYPE
from tg.decorators import expose, validate
from formencode import validators
from tg import expose, redirect, config
from pylons import c
from tg.controllers import TGController
from formencode import validators as fev
from nose.tools import eq_

import ew
import ew.dojo
from ew.core import variable_decode

@expose('ew.tests.templates.template_test')
def echo_parms(**kw):
    return dict(value=kw)

@expose('ew.tests.templates.bad_template_test')
def bad_template(**kw):
    return dict(value=kw)

@expose('json')
@validate(dict(a=fev.Number(if_missing=None), b=fev.Number(if_missing=None)))
def echo_parms_validated(**kw):
    return kw

class WeirdValidator(object):

    def to_python(self, value, state):
        return int(value[0])

    def from_python(self, value, state):
        return '%d-asdf' % value

class BigTestForm(ew.SimpleForm):
    class fields(ew.WidgetsList):
        f0 = ew.HiddenField(if_missing=None)
        f1 = ew.TextField(if_missing=None)
        f2 = ew.EmailField(if_missing=None)
        f3 = ew.NumberField(if_missing=None)
        f4 = ew.IntField(if_missing=None)
        f5 = ew.DateField(if_missing=None)
        f6 = ew.TimeField(if_missing=None)
        f7 = ew.TextArea(if_missing=None)
        f8 = ew.Checkbox(if_missing=None)
        f9 = ew.LinkField()
        fa = ew.HTMLField()

class IntForm(ew.SimpleForm):
    class fields(ew.WidgetsList):
        x = ew.IntField()

class RootController(TGController):
    text_field = ew.TextField(name='foo', validator=fev.UnicodeString(min=5))
    easy_form = ew.SimpleForm(fields=[text_field])
    nested_form = ew.SimpleForm(fields=[
            ew.CompoundField(name='foo', fields=[
                    ew.TextField(name='a', validator=fev.UnicodeString(min=5)),
                    ew.TextField(name='b', validator=fev.UnicodeString(min=5))
                    ])
            ])
    repeated_form = ew.SimpleForm(fields=[
            ew.RepeatedField(field=ew.TextField(name='a', validator=fev.UnicodeString(min=5)),
                             repetitions=5)])
    nested_fieldsets = ew.SimpleForm(fields=[
            ew.FieldSet(name='foo', label='Foo', fields=[
                    ew.TextField(name='a', validator=fev.UnicodeString(min=5)),
                    ew.TextField(name='b', validator=fev.UnicodeString(min=5))
                    ]),
            ew.FieldSet(label='Bar', fields=[
                    ew.TextField(name='c', validator=fev.UnicodeString(min=5)),
                    ew.TextField(name='d', validator=fev.UnicodeString(min=5))
                    ])
            ])
    table = ew.SimpleForm(fields=[
            ew.TableField(field=ew.RowField(name='foo', fields=[
                        ew.TextField(name='a', validator=fev.UnicodeString(min=5)),
                        ew.TextField(name='b', validator=fev.UnicodeString(min=5))
                        ]),
                      repetitions=5)
            ])
    select_form = ew.SimpleForm(fields=[
            ew.SingleSelectField(name='a', options=range(5), if_missing=0),
            ew.MultiSelectField(name='b', options=lambda:range(5), if_missing=0),
            ew.SingleSelectField(name='c', options=[
                    ew.Option(py_value=1), ew.Option(py_value=2), ],
                                 validator=WeirdValidator(),
                                 if_missing=1)
            ])
    big_test_form = BigTestForm()
    int_form = IntForm()

    def __init__(self):
        self._ew_resources = ew.ResourceManager.get()
        self.res = ResourceController()

    @expose()
    def index(self, **kwargs):
        return ew.WidgetInstance(ew.ControllerWidget(echo_parms),
                                 dict(value=kwargs)).display()

    @expose()
    def index_input(self, **kwargs):
        return ew.WidgetInstance(self.text_field).display()

    @expose()
    def index_form(self, **kwargs):
        return ew.WidgetInstance(self.easy_form).display()

    @expose()
    def index_repeated(self, **kwargs):
        return ew.WidgetInstance(self.repeated_form).display()

    @expose()
    def index_nested_form(self, **kwargs):
        return ew.WidgetInstance(self.nested_form).display()

    @expose()
    def index_nested_fs(self, **kwargs):
        return ew.WidgetInstance(self.nested_fieldsets).display()

    @expose()
    def index_table(self, **kwargs):
        return ew.WidgetInstance(self.table).display()

    @expose()
    def index_cw(self, **kwargs):
        w = ew.ControllerWidget(echo_parms_validated)
        return w.display(**kwargs)

    @expose()
    def index_bad_template(self, **kwargs):
        return ew.WidgetInstance(ew.ControllerWidget(bad_template),
                                 dict(value=kwargs)).display()


    @expose('ew.tests.templates.double_form')
    @variable_decode
    def index_double_form(self, **kwargs):
        c.form = self.int_form
        return dict(
            a=dict(x=5),
            b=dict(x=15))

    @expose()
    @variable_decode
    @validate(select_form)
    def index_select_form(self, **kwargs):
        return self.select_form.display(value=kwargs)

    @expose()
    @variable_decode
    @validate(big_test_form)
    def index_bigtest_form(self, **kwargs):
        return self.big_test_form.display(value=kwargs)

    ############################################################

    @expose()
    @validate(easy_form, error_handler=index_form)
    def validate_input(self, foo=None, **kw):
        return foo

    @expose('json')
    @variable_decode
    @validate(nested_form, error_handler=index_nested_form)
    def validate_nested(self, **kw):
        return kw

    @expose('json')
    @variable_decode
    @validate(repeated_form, error_handler=index_repeated)
    def validate_repeated(self, **kw):
        return kw

    @expose('json')
    @variable_decode
    @validate(nested_fieldsets, error_handler=index_nested_fs)
    def validate_nested_fs(self, **kw):
        return kw

    @expose('json')
    @variable_decode
    @validate(table, error_handler=index_table)
    def validate_table(self, **kw):
        return kw

    @expose('json')
    @variable_decode
    @validate(ew.ControllerWidget(echo_parms_validated),
              error_handler=index_cw)
    def validate_cw(self, **kwargs):
        return kwargs

    @expose('json')
    @variable_decode
    @validate(IntForm(name='a'), error_handler=index_double_form)
    def validate_double_a(self, **kwargs):
        return kwargs

    @expose('json')
    @variable_decode
    @validate(IntForm(name='b'), error_handler=index_double_form)
    def validate_double_b(self, **kwargs):
        return kwargs

class ResourceController(object):

    form = ew.SimpleForm(fields=[
            ew.dojo.TextField(name='a')])

    @expose('ew.tests.templates.resource_index')
    def index(self):
        c.form = self.form
        return dict()

