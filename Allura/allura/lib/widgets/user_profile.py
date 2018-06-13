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

import logging
import re

import ew as ew_core
import ew.jinja2_ew as ew
import tg
from formencode import validators as fev

from allura.lib import helpers as h
from .forms import ForgeForm

log = logging.getLogger(__name__)


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

        cc = ew.Checkbox(label='Send me a copy')


class SectionsUtil(object):

    @staticmethod
    def load_sections(app):
        sections = {}
        for ep in h.iter_entry_points('allura.%s.sections' % app):
            sections[ep.name] = ep.load()
        section_ordering = tg.config.get('%s_sections.order' % app, '')
        ordered_sections = []
        for section in re.split(r'\s*,\s*', section_ordering):
            if section in sections:
                ordered_sections.append(sections.pop(section))
        sections = ordered_sections + sections.values()
        return sections
