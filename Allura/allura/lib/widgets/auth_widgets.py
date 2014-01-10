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

from pylons import request
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
            ew.TextField(name='username', label='Username'),
            ew.PasswordField(name='password', label='Password')
        ]
        if plugin.AuthenticationProvider.get(request).forgotten_password_process:
            # only show link if auth provider has method of recovering password
            fields.append(
                ew.HTMLField(name='link', text='<a href="forgotten_password">Forgot password?</a>'))
        return fields

    class hidden_fields(ew_core.NameList):
        return_to = ew.HiddenField()

    @validator
    def validate(self, value, state=None):
        try:
            value['username'] = plugin.AuthenticationProvider.get(
                request).login()
        except exc.HTTPUnauthorized:
            msg = 'Invalid login'
            raise Invalid(
                msg,
                dict(username=value['username']),
                None)
        return value


class ForgottenPasswordForm(ForgeForm):
    submit_text = 'Recover password'
    style = 'wide'

    class fields(ew_core.NameList):
        email = ew.TextField(label='Your e-mail')

    @validator
    def validate(self, value, state=None):
        email = value['email']
        email_record = M.EmailAddress.query.find({'_id': email}).first()
        user = M.User.by_email_address(email)
        if user is None or not email_record.confirmed:
            raise Invalid(
                'Unable to recover password for this email',
                {'email': email}, None)
        return value
