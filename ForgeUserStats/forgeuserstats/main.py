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
from tg import tmpl_context as c
from datetime import datetime

from allura.app import Application, SitemapEntry
from allura.lib import helpers as h
from allura import model as M
from allura.eventslistener import EventsListener
from .model.stats import UserStats
from .controllers.userstats import ForgeUserStatsController

from forgeuserstats import version

from ming.orm import session

log = logging.getLogger(__name__)


class UserStatsListener(EventsListener):

    def newArtifact(self, art_type, art_datetime, project, user):
        stats = user.stats
        if not stats:
            stats = UserStats.create(user)
        stats.addNewArtifact(art_type, art_datetime, project)

    def modifiedArtifact(self, art_type, art_datetime, project, user):
        stats = user.stats
        if not stats:
            stats = UserStats.create(user)

        stats.addModifiedArtifact(art_type, art_datetime, project)

    def newUser(self, user):
        UserStats.create(user)

    def ticketEvent(self, event_type, ticket, project, user):
        if user is None:
            return
        stats = user.stats
        if not stats:
            stats = UserStats.create(user)

        if event_type == "assigned":
            stats.addAssignedTicket(ticket.mod_date, project)
        elif event_type == "revoked":
            stats.addRevokedTicket(ticket.mod_date, project)
        elif event_type == "closed":
            stats.addClosedTicket(
                ticket.created_date, ticket.mod_date, project)

    def newCommit(self, newcommit, project, user):
        stats = user.stats
        if not stats:
            stats = UserStats.create(user)

        stats.addCommit(newcommit, datetime.utcnow(), project)

    def addUserLogin(self, user):
        stats = user.stats
        if not stats:
            stats = UserStats.create(user)

        stats.addLogin(datetime.utcnow())

    def newOrganization(self, organization):
        pass


class ForgeUserStatsApp(Application):
    __version__ = version.__version__
    tool_label = 'UserStats'
    default_mount_label = 'Stats'
    default_mount_point = 'stats'
    permissions = ['configure', 'read', 'write',
                   'unmoderated_post', 'post', 'moderate', 'admin']
    permissions_desc = {
        'read': 'View user stats.',
        'admin': 'Toggle stats visibility.',
    }
    max_instances = 0
    has_notifications = False
    ordinal = 15
    config_options = Application.config_options
    default_external_feeds = []
    icons = {
        24: 'userstats/images/stats_24.png',
        32: 'userstats/images/stats_32.png',
        48: 'userstats/images/stats_48.png'
    }
    root = ForgeUserStatsController()

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        role_admin = M.ProjectRole.by_name('Admin', project)._id
        role_anon = M.ProjectRole.by_name('*anonymous', project)._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_admin, 'admin')]

    def main_menu(self):
        return [SitemapEntry(self.config.options.mount_label, '.')]

    def is_visible_to(self, user):
        # we don't work with user subprojects
        return c.project.is_root

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()]]

    @property
    def show_discussion(self):
        if 'show_discussion' in self.config.options:
            return self.config.options['show_discussion']
        else:
            return True

    @h.exceptionless([], log)
    def sidebar_menu(self):
        base = c.app.url
        links = [SitemapEntry('Overview', base),
                 SitemapEntry('Commits', base + 'commits'),
                 SitemapEntry('Artifacts', base + 'artifacts'),
                 SitemapEntry('Tickets', base + 'tickets')]
        return links

    def admin_menu(self):
        links = [SitemapEntry(
            'Settings', c.project.url() + 'userstats/settings')]
        return links

    def install(self, project):
        # It doesn't make any sense to install the tool twice on the same
        # project therefore, if it already exists, it doesn't install it
        # a second time.
        for tool in project.app_configs:
            if tool.tool_name == 'userstats':
                if self.config.options.mount_point != tool.options.mount_point:
                    project.uninstall_app(self.config.options.mount_point)
                    return

    def uninstall(self, project):
        self.config.delete()
        session(self.config).flush()
