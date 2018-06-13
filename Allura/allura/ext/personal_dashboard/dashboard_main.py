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

import tg
from jinja2 import Markup
from paste.deploy.converters import asbool
from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c
from tg import expose, redirect

from allura.controllers import BaseController
from allura.controllers.feed import FeedController
from allura.lib import helpers as h
from allura.lib.plugin import AuthenticationProvider
from allura.lib.widgets.user_profile import SectionsUtil

log = logging.getLogger(__name__)


class DashboardController(BaseController, FeedController):

    @expose('jinja:allura.ext.personal_dashboard:templates/dashboard_index.html')
    def index(self, **kw):
        if not c.user.is_anonymous():
            user = c.user
            sections = [section(user)
                        for section in SectionsUtil.load_sections('personal_dashboard')]
            return dict(user=user, sections=sections, title="Personal Dashboard")
        else:
            redirect('/neighborhood')


class DashboardSectionBase(object):
    """
    This is the base class for sections on the Dashboard tool.

    .. py:attribute:: template

       A resource string pointing to the template for this section.  E.g.::

           template = "allura.ext.personal_dashboard:templates/projects.html"

    Sections must be pointed to by an entry-point in the group
    ``[allura.personal_dashboard.sections]``.
    """
    template = ''

    def __init__(self, user):
        """
        Creates a section for the given :param:`user`. Stores the values as attributes of
        the same name.
        """
        self.user = user

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

    def display(self, *a, **kw):
        """
        Renders the section using the context from :meth:`prepare_context`
        and the :attr:`template`, if :meth:`check_display` returns True.

        If overridden or this base class is not used, this method should
        return either plain text (which will be escaped) or a `jinja2.Markup`
        instance.
        """
        if not self.check_display():
            return ''
        try:
            tmpl = g.jinja2_env.get_template(self.template)
            context = self.prepare_context({
                'h': h,
                'c': c,
                'g': g,
                'user': self.user,
                'config': tg.config,
                'auth': AuthenticationProvider.get(request),
            })
            return Markup(tmpl.render(context))
        except Exception as e:
            log.exception('Error rendering profile section %s: %s', type(self).__name__, e)
            if asbool(tg.config.get('debug')):
                raise
            else:
                return ''


class ProjectsSection(DashboardSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/projects.html'


class TicketsSection(DashboardSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/tickets.html'


class MergeRequestsSection(DashboardSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/merge_requests.html'


class FollowersSection(DashboardSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/followers.html'
