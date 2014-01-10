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
from formencode import validators as fev
from .forms import ForgeForm


class SendMessageForm(ForgeForm):
    template = 'jinja:allura.ext.user_profile:templates/send_message_form.html'
    submit_text = 'Send Message'

    class fields(ew_core.NameList):
        subject = ew.TextField(
            validator=fev.UnicodeString(
                not_empty=True,
                messages={'empty': "You must provide a Subject"}),
            attrs=dict(
                placeholder='Enter your subject here',
                title='Enter your subject here',
                style='width: 425px'),
            label='Subject')

        message = ew.TextArea(
            validator=fev.UnicodeString(
                not_empty=True,
                messages={'empty': "You must provide a Message"}),
            attrs=dict(
                placeholder='Enter your message here',
                title='Enter your message here',
                style='width: 425px; height:200px'),
            label='Message')

        cc = ew.Checkbox(label='CC Sender')
