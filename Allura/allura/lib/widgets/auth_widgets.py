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
from formencode import Invalid, validators
from webob import exc

from .forms import ForgeForm

from allura.lib import plugin
from allura import model as M

class LoginForm(ForgeForm):
    submit_text='Login'
    style='wide'
    class fields(ew_core.NameList):
        username = ew.TextField(label='Username')
        password = ew.PasswordField(label='Password')
        if plugin.LocalAuthenticationProvider.forgotten_password_process:
            link = ew.HTMLField(text='<a href="./forgotten_password">Forgot password?</a>')

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


class ForgottenPasswordForm(ForgeForm):
    submit_text='Recover password'
    style='wide'

    class fields(ew_core.NameList):
        email = ew.TextField(label='Your e-mail')

    @validator
    def validate(self, value, state=None):
        email = value['email']
        record = M.EmailAddress.query.find({'_id': email}).first()
        if not record:
            raise Invalid(
                "Email doesn't exists",
                dict(email=value['email']),
                None)
        user_record = M.User.query.find({'_id': record.claimed_by_user_id}).first()
        if not record.confirmed or not user_record or user_record.disabled:
            raise Invalid(
                "Email doesn't verified or user record disabled",
                dict(email=value['email']),
                None)
        return value

class RecoverPasswordChangeForm(ForgeForm):
    class fields(ew_core.NameList):
        pw = ew.PasswordField(
            label='New Password',
            validator=validators.UnicodeString(not_empty=True, min=6))
        pw2 = ew.PasswordField(
            label='New Password (again)',
            validator=validators.UnicodeString(not_empty=True))

    @validator
    def to_python(self, value, state):
        d = super(RecoverPasswordChangeForm, self).to_python(value, state)
        if d['pw'] != d['pw2']:
            raise Invalid('Passwords must match', value, state)
        return d
