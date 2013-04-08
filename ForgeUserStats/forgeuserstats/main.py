#-*- python -*-
import logging
from pylons import tmpl_context as c
import formencode
from formencode import validators
from webob import exc
from datetime import datetime

from allura.app import Application, SitemapEntry
from allura.lib import helpers as h
from allura.lib.security import has_access
from allura import model as M
from allura.eventslistener import EventsListener
from model.stats import UserStats
from controllers.userstats import ForgeUserStatsController

from forgeuserstats import version
from forgeuserstats.controllers.userstats import ForgeUserStatsController

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
        stats = UserStats.create(user)

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
            stats.addClosedTicket(ticket.created_date,ticket.mod_date,project)

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
    tool_label='UserStats'
    default_mount_label='Stats'
    default_mount_point='stats'
    permissions = ['configure', 'read', 'write',
                    'unmoderated_post', 'post', 'moderate', 'admin']
    ordinal=15
    installable=False
    config_options = Application.config_options
    default_external_feeds = []
    icons={
        24:'../../tool/userstats/images/stats_24.png',
        32:'../../tool/userstats/images/stats_32.png',
        48:'../../tool/userstats/images/stats_48.png'
    }
    root = ForgeUserStatsController()

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_admin, 'admin')]

    def main_menu(self):
        return [SitemapEntry(self.config.options.mount_label, '.')]

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

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
        #It doesn't make any sense to install the tool twice on the same
        #project therefore, if it already exists, it doesn't install it
        #a second time.
        for tool in project.app_configs:
            if tool.tool_name == 'userstats':
                if self.config.options.mount_point!=tool.options.mount_point:
                    project.uninstall_app(self.config.options.mount_point)
                    return

    def uninstall(self, project):
        self.config.delete()
        session(self.config).flush()
