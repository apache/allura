import urlparse
try:
    import json
except ImportError:
    import simplejson as json

import pkg_resources
from pylons import c
from tg import expose
from formencode import validators as fev

from ew import core
from ew import fields
from ew import select
from ew import forms
from ew import resource

class Currency(fev.Number):
    symbol=u'$'
    format=u'%.2f'
    store_factor=100

    def _to_python(self, value, state):
        value = value.strip(u' \r\n\t' + self.symbol)
        return int(fev.Number._to_python(self, value, state) * self.store_factor)
    def from_python(self, value, state):
        if isinstance(value, basestring):
            return value
        elif isinstance(value, (int, float, long)):
            value = float(value) / self.store_factor
            return self.format  % value

class DojoConfig(resource.ResourceScript):
    params = dict(parseOnLoad=True, modulePaths={})
    dojo_js='http://ajax.googleapis.com/ajax/libs/dojo/1.3/dojo/dojo.xd.js'

    class __metaclass__(type):
        def __setitem__(cls, k, v):
            cls.params[k] = v
        def __getitem__(cls, k):
            return cls.params[k]

    def __init__(self):
        super(DojoConfig, self).__init__('', 'head_js', True, True)

    @expose('genshi:ew.templates.dojo.dojo_config')
    def index(self, **kw):
        return dict(json_config = self._json_params())

    @classmethod
    def url_for(cls, module, resource):
        base = cls['modulePaths'].get(module, None)
        if base is None:
            base = '../%s' % module
        base = urlparse.urljoin(cls.dojo_js, base)
        return base + resource

    def _json_params(self):
        params = {}
        for k,v in self.params.iteritems():
            if callable(v): v = v()
            params[k] = v
        return json.dumps(params)

    @classmethod
    def compressed(cls, manager, resources):
        return resource.JSScript.compressed(
            manager,
            [ resource.JSScript('djConfig = %s' % r._json_params()) for r in resources])

class Require(resource.JSScript):
    def __init__(self, module):
        text = "dojo.require('%s')" % module
        super(Require, self).__init__(text, 'body_js')
    def __repr__(self):
        return self.text
    @classmethod
    def compressed(cls, manager, resources):
        return resources

class DojoField(core.Widget):
    theme='soria'
    dojoRequires = []
    params=['dojoType', 'hint']
    dojoType=None
    hint=None

    def resources(self):
        config = DojoConfig()
        for x in super(DojoField, self).resources(): yield x
        yield resource.CSSLink(config.url_for('dojo', '/resources/dojo.css'))
        yield resource.CSSLink(config.url_for('dijit', '/themes/%s/%s.css' % (self.theme, self.theme)))
        yield DojoConfig()
        yield resource.JSLink(config.dojo_js)
        for r in self.dojoRequires:
            yield Require(r)

class DateField(fields.DateField, DojoField):
    template='genshi:ew.templates.dojo.input_field'
    attrs = { 'style':'width:6.5em' }
    dojoType='dijit.form.DateTextBox'
    dojoRequires = [ 'dijit.form.DateTextBox' ]

class TimeField(fields.TimeField, DojoField):
    template='genshi:ew.templates.dojo.input_field'
    attrs = { 'style':'width:5.5em' }
    dojoType='dijit.form.TimeTextBox'
    dojoRequires=['dijit.form.TimeTextBox']

class TextField(fields.TextField, DojoField):
    template='genshi:ew.templates.dojo.input_field'
    params=['hint', 'dojoType']
    dojoType='dijit.form.ValidationTextBox'
    dojoRequires = ['dijit.form.ValidationTextBox']
    hint=None

class TextArea(fields.TextArea, DojoField):
    attrs=dict(dojoType='dijit.form.Textarea')
    dojoRequires = [ 'dijit.form.Textarea' ]
    cols=60

class PasswordField(TextField):
    attrs=dict(type='password')

class IntegerField(TextField):
    validator = fev.Int()
    attrs=dict(style='width:6em;')
    dojoType='dijit.form.NumberTextBox'
    dojoRequires = [ 'dijit.form.NumberTextBox' ]

class CurrencyField(TextField):
    validator=Currency()
    dojoType='dijit.form.CurrencyTextBox'
    dojoRequires = [ 'dijit.form.CurrencyTextBox' ]
    attrs=dict(currency='USD')

class Checkbox(fields.Checkbox, DojoField):
    attrs=dict(dojoType='dijit.form.CheckBox')
    dojoRequires=['dijit.form.CheckBox']

class EmailField(TextField):
    validator=fev.Email()

class SingleSelectField(select.SingleSelectField, DojoField):
    attrs=dict(dojoType='dijit.form.FilteringSelect')
    params=['prompt']
    prompt=None
    dojoRequires=['dijit.form.FilteringSelect']

    def __init__(self, **kw):
        self._attrs = {}
        super(SingleSelectField, self).__init__(**kw)

    def _get_attrs(self):
        return dict(self._attrs, promptMessage=self.prompt)

class CheckboxSet(select.CheckboxSet, DojoField):
    template='genshi:ew.templates.dojo.checkbox_set'
    dojoRequires=['dijit.form.CheckBox']

class SubmitButton(fields.SubmitButton, DojoField):
    template='genshi:ew.templates.dojo.submit_button'
    params=['prompt']
    prompt=''
    dojoRequires=['dijit.form.Button']

class ArrowButton(fields.SubmitButton, DojoField):
    template='genshi:ew.templates.dojo.arrow_button'
    params=['direction']
    direction='u'
    dojoRequires=['dijit.form.Button']

class DeleteButton(fields.SubmitButton, DojoField):
    template='genshi:ew.templates.dojo.icon_button'
    params=['iconClass']
    iconClass = 'delete-button'
    dojoRequires=['dijit.form.Button']

class SimpleForm(forms.SimpleForm, DojoField):
    template='genshi:ew.templates.dojo.simple_form'
    button_class = SubmitButton

    def __init__(self, **kw):
        super(SimpleForm, self).__init__(**kw)
        for b in self.buttons:
            if b.attrs is None:
                b.attrs = {}
            else:
                b.attrs = dict(b.attrs)

class SimpleArea(forms.SimpleForm, DojoField):
    template='genshi:ew.templates.dojo.simple_area'

class Wizard(SimpleForm):
    template='genshi:ew.templates.wizard'
