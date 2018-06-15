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

from pylons import tmpl_context as c
from tg import expose, redirect

from allura.controllers import BaseController
from allura.controllers.feed import FeedController
from allura.lib.widgets.user_profile import SectionBase
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


class DashboardSectionBase(SectionBase):
    """
    This is the base class for sections on the Dashboard tool.

    .. py:attribute:: template

       A resource string pointing to the template for this section.  E.g.::

           template = "allura.ext.personal_dashboard:templates/projects.html"

    Sections must be pointed to by an entry-point in the group
    ``[allura.personal_dashboard.sections]``.
    """


class ProjectsSection(DashboardSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/projects.html'


class TicketsSection(DashboardSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/tickets.html'


class MergeRequestsSection(DashboardSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/merge_requests.html'


class FollowersSection(DashboardSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/followers.html'
