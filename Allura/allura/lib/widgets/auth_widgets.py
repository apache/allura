import ew as ew_core
import ew.jinja2_ew as ew
from ew.core import validator

from tg import request
from formencode import Invalid
from webob import exc

from .forms import ForgeForm

from allura.lib import plugin

class LoginForm(ForgeForm):
    submit_text='Login'
    style='wide'
    class fields(ew_core.NameList):
        username = ew.TextField(label='Username')
        password = ew.PasswordField(label='Password')
    class hidden_fields(ew_core.NameList):
        return_to = ew.HiddenField()

    @validator
    def validate(self, value, state=None):
        try:
            value['username'] = plugin.AuthenticationProvider.get(request).login()
        except exc.HTTPUnauthorized:
            msg = 'Invalid login'
            raise Invalid(
                msg,
                dict(username=value['username']),
                None)
        return value
