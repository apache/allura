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

from pylons import request, tmpl_context as c
from formencode import Invalid
from webob import exc

from .forms import ForgeForm

from allura.lib import plugin
from allura import model as M


class LoginForm(ForgeForm):
    submit_text = 'Login'
    style = 'wide'

    @property
    def fields(self):
        fields = [
            ew.TextField(name='username', label='Username', attrs={
                'autofocus': 'autofocus',
            }),
            ew.PasswordField(name='password', label='Password'),
            ew.Checkbox(
                name='rememberme',
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
        return fields

    @validator
    def validate(self, value, state=None):
        try:
            value['username'] = plugin.AuthenticationProvider.get(request).login()
        except exc.HTTPUnauthorized:
            msg = 'Invalid login'
            raise Invalid(
                msg,
                dict(username=value['username'], rememberme=value.get('rememberme'),
                     return_to=value.get('return_to')),
                None)
        except exc.HTTPBadRequest as e:
            raise Invalid(
                e.message,
                dict(username=value['username'], rememberme=value.get('rememberme'),
                     return_to=value.get('return_to')),
                None)
        return value


class ForgottenPasswordForm(ForgeForm):
    submit_text = 'Recover password'
    style = 'wide'

    class fields(ew_core.NameList):
        email = ew.TextField(label='Your e-mail')

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
