#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import ew as ew_core
import ew.jinja2_ew as ew
from ew.core import validator

from tg import request, tmpl_context as c
from formencode import Invalid
from formencode import validators as fev
from webob import exc

from .forms import ForgeForm
from tg import tmpl_context as c, app_globals as g

from allura.lib import plugin
from allura import model as M


class LoginForm(ForgeForm):
    submit_text = 'Login'
    style = 'wide'

    @property
    def fields(self):
        fields = [
            ew.TextField(name=g.antispam.enc('username'), label='Username', attrs={
                'autofocus': 'autofocus',
                'placeholder': 'Username' if plugin.ThemeProvider.get().use_input_placeholders() else '',
                'autocomplete': 'username',
                'autocapitalize': 'none',
            }),
            ew.PasswordField(name=g.antispam.enc('password'), label='Password', attrs={
                'placeholder': 'Password' if plugin.ThemeProvider.get().use_input_placeholders() else '',
                'autocomplete': 'current-password',
            }),
            ew.Checkbox(
                name=g.antispam.enc('rememberme'),
                label='Remember Me',
                attrs={'style': 'margin-left: 162px;'}),
            ew.HiddenField(name='return_to'),
        ]
        if plugin.AuthenticationProvider.get(request).forgotten_password_process:
            # only show link if auth provider has method of recovering password
            fields.append(
                ew.HTMLField(
                    name='link',
                    text='<a href="/auth/forgotten_password" style="margin-left:162px" target="_top">'
                         'Forgot password?</a>'))

        for fld in g.antispam.extra_fields():
            fields.append(
                ew_core.Widget(template=ew.Snippet(fld)))

        return fields

    @validator
    def validate(self, value, state=None):
        super().validate(value, state=state)
        auth_provider = plugin.AuthenticationProvider.get(request)

        # can't use a validator attr on the username TextField, since the antispam encoded name changes and doesn't
        # match the name used in the form submission
        auth_provider.username_validator(long_message=False).to_python(value['username'])

        try:
            auth_provider.login()
        except exc.HTTPUnauthorized:
            msg = 'Invalid login'
            raise Invalid(
                msg,
                dict(username=value['username'], rememberme=value.get('rememberme'),
                     return_to=value.get('return_to')),
                None)
        except exc.HTTPBadRequest as e:
            raise Invalid(
                e.args[0],
                dict(username=value['username'], rememberme=value.get('rememberme'),
                     return_to=value.get('return_to')),
                None)
        return value


class ForgottenPasswordForm(ForgeForm):
    submit_text = 'Recover password'
    style = 'wide'

    class fields(ew_core.NameList):
        email = ew.TextField(label='Your e-mail', attrs={'type': 'email', 'required': True, 'autocapitalize': "none"})


class DisableAccountForm(ForgeForm):
    submit_text = 'Disable'

    class fields(ew_core.NameList):
        password = ew.PasswordField(name='password', label='Account password')

    @validator
    def validate(self, value, state=None):
        provider = plugin.AuthenticationProvider.get(request)
        if not provider.validate_password(c.user, value['password']):
            raise Invalid('Invalid password', {}, None)
        return value
