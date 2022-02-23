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

import ew.jinja2_ew as ew

from formencode import validators as fev
from allura.lib import validators as v
from allura.lib.widgets import forms as ff
from allura.lib.widgets import form_fields as ffw


class OptionsAdmin(ff.AdminForm):
    template = 'jinja:forgetracker:templates/tracker_widgets/options_admin.html'
    defaults = dict(
        ff.ForgeForm.defaults,
        submit_text='Save')

    @property
    def fields(self):
        fields = [
            ew.Checkbox(
                name='EnableVoting',
                label='Enable voting on tickets'),
            ew.Checkbox(
                name='AllowEmailPosting',
                label='Allow posting replies via email'),
            ew.TextField(
                name='TicketMonitoringEmail',
                label='Email ticket notifications to',
                validator=fev.Email(),
                grid_width='7'),
            ew.SingleSelectField(
                name='TicketMonitoringType',
                label='Send notifications for',
                grid_width='7',
                options=[
                    ew.Option(py_value='NewTicketsOnly',
                              label='New tickets only'),
                    ew.Option(py_value='NewPublicTicketsOnly',
                              label='New public tickets only'),
                    ew.Option(py_value='AllTicketChanges',
                              label='All ticket changes'),
                    ew.Option(py_value='AllPublicTicketChanges',
                              label='All public ticket changes'),
                ]),
            ffw.MarkdownEdit(
                name='TicketHelpNew',
                label='Help text to display on new ticket page',
                validator=v.String(),
                attrs={'style': 'width: 95%'}),
            ffw.MarkdownEdit(
                name='TicketHelpSearch',
                label='Help text to display on ticket list pages (index page,'
                      ' search results, milestone lists)',
                validator=v.String(),
                attrs={'style': 'width: 95%'}),
        ]
        return fields
