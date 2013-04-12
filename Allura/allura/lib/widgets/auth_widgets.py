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
