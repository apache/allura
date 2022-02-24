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

from tg import tmpl_context as c, app_globals as g
from tg import expose, redirect, config
from itertools import islice
from ming.orm import session

from allura.model.timeline import perm_check, get_activity_object
from allura.controllers import BaseController
from allura.controllers.feed import FeedController
from allura.lib.widgets.user_profile import SectionBase, SectionsUtil, ProjectsSectionBase
from allura.lib.widgets import form_fields as ffw
from paste.deploy.converters import asbool

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


class ProjectsSection(DashboardSectionBase, ProjectsSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/projects.html'


class TicketsSection(DashboardSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/tickets.html'

    def query_tickets(self, page, limit):
        from forgetracker.model import Ticket

        q = ' OR '.join(['assigned_to:' + str(self.user['username']), 'reported_by:' + str(self.user['username'])])
        sort = 'mod_date_dt desc'
        result = Ticket.paged_search(None, self.user, q, limit=limit, page=page, sort=sort)

        tickets = [
            dict(
                ticket_num=ticket['ticket_num'],
                url=ticket.url(),
                summary=ticket['summary'],
                mod_date=ticket['mod_date'],
                reported_by=ticket['reported_by'],
                assigned_to_id=ticket['assigned_to_id'],
                assigned_to=ticket['assigned_to'],
                status=ticket['status'])
            for ticket in result.get('tickets')
        ]
        return dict(tickets=tickets, count=result.get('count'), solr_error=result.get('solr_error'))

    def prepare_context(self, context):
        page = 0
        limit = 25

        page_string = context['c'].form_values.get('page')
        limit_string = context['c'].form_values.get('limit')
        if page_string is not None:
            page = int(page_string)
        if limit_string is not None:
            limit = int(limit_string)
        result = self.query_tickets(page, limit)
        context['page_size'] = ffw.PageSize()
        context['page_list'] = ffw.PageList()
        context['page'] = page
        context['limit'] = limit
        context['tickets'] = result.get('tickets')
        context['count'] = result.get('count')
        context['solr_error'] = result.get('solr_error')
        return context


class MergeRequestsSection(DashboardSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/merge_requests.html'

    def get_merge_requests(self):
        return [
            merge_request
            for merge_request in self.user.my_merge_requests()]

    def prepare_context(self, context):
        context['requests'] = self.get_merge_requests()
        return context

    def __json__(self):
        merge_requests = [
            dict(
                status=merge_request['status'],
                summary=merge_request['summary'],
                repository=merge_request['repository'],
                created=merge_request['created'],
                updated=merge_request['updated'])
            for merge_request in self.get_merge_requests()]
        return dict(merge_requests=merge_requests)


class ActivitySection(DashboardSectionBase):
    template = 'allura.ext.personal_dashboard:templates/sections/activity.html'

    def __init__(self, user):
        super(DashboardSectionBase, self).__init__(user)
        self.activity_app = c.user.private_project().app_instance('activity')

    def check_display(self):
        app_installed = self.activity_app is not None
        activity_enabled = asbool(config.get('activitystream.enabled', False))
        return app_installed and activity_enabled

    def prepare_context(self, context):
        full_timeline = g.director.get_timeline(
            self.user, page=0, limit=100,
            actor_only=False,
        )
        filtered_timeline = list(islice(filter(perm_check(c.user), full_timeline),
                                        0, 8))
        for activity in filtered_timeline:
            # Get the project for the activity.obj so we can use it in the
            # template. Expunge first so Ming doesn't try to flush the attr
            # we create to temporarily store the project.
            #
            # The get_activity_object() calls are cheap, pulling from
            # the session identity map instead of mongo since identical
            # calls are made by perm_check() above.
            session(activity).expunge(activity)
            activity_obj = get_activity_object(activity.obj)
            activity.obj.project = getattr(activity_obj, 'project', None)

        context['timeline'] = filtered_timeline
        context['activity_app'] = self.activity_app

        return context
