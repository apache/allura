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
from markupsafe import Markup
from paste.deploy.converters import asbool
import tg
from tg import app_globals as g
from tg import request
from tg import tmpl_context as c

from allura.lib import helpers as h
from allura.lib import validators as v
from allura.lib.plugin import AuthenticationProvider
from .forms import ForgeForm

log = logging.getLogger(__name__)


class SendMessageForm(ForgeForm):
    template = 'jinja:allura.ext.user_profile:templates/send_message_form.html'
    submit_text = 'Send Message'

    class fields(ew_core.NameList):
        subject = ew.TextField(
            validator=v.UnicodeString(
                not_empty=True,
                messages={'empty': "You must provide a Subject"}),
            attrs=dict(
                placeholder='Enter your subject here',
                title='Enter your subject here',
                style='width: 425px'),
            label='Subject')

        message = ew.TextArea(
            validator=v.UnicodeString(
                not_empty=True,
                messages={'empty': "You must provide a Message"}),
            attrs=dict(
                placeholder='Enter your message here',
                title='Enter your message here',
                style='width: 425px; height:200px'),
            label='Message')

        cc = ew.Checkbox(label='Send me a copy')
        reply_to_real_address = ew.Checkbox(label='Include my email address in the reply field for this message')


class SectionsUtil:

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
        sections = ordered_sections + list(sections.values())
        return sections


class SectionBase:
    """
    This is the base class for sections in Profile tool and Dashboard.
    """
    template = ''

    def __init__(self, user):
        """
        Creates a section for the given :param:`user`. Stores the values as attributes of
        the same name.
        """
        self.user = user
        self.context = None

    def check_display(self):
        """
        Should return True if the section should be displayed.
        """
        return True

    def prepare_context(self, context):
        """
        Should be overridden to add any values to the template context prior
        to display.
        """
        return context

    def setup_context(self):
        self.context = self.prepare_context({
            'h': h,
            'c': c,
            'g': g,
            'user': self.user,
            'config': tg.config,
            'auth': AuthenticationProvider.get(request),
        })

    def display(self, *a, **kw):
        """
        Renders the section using the context from :meth:`prepare_context`
        and the :attr:`template`, if :meth:`check_display` returns True.

        If overridden or this base class is not used, this method should
        return either plain text (which will be escaped) or a `marksupsafe.Markup`
        instance.
        """
        if not self.check_display():
            return ''
        try:
            tmpl = g.jinja2_env.get_template(self.template)
            if not self.context:
                self.setup_context()
            return Markup(tmpl.render(self.context))
        except Exception as e:
            log.exception('Error rendering section %s: %s', type(self).__name__, e)
            if asbool(tg.config.get('debug')):
                raise
            else:
                return ''


class ProjectsSectionBase(SectionBase):

    def get_projects(self):
        return [
            project
            for project in self.user.my_projects()
            if project != c.project
               and (self.user == c.user or h.has_access(project, 'read'))
               and not project.is_nbhd_project
               and not project.is_user_project]

    def prepare_context(self, context):
        context['projects'] = self.get_projects()
        return context

    def __json__(self):
        projects = [
            dict(
                name=project['name'],
                url=project.url(),
                summary=project['summary'],
                last_updated=project['last_updated'])
            for project in self.get_projects()]
        return dict(projects=projects)
