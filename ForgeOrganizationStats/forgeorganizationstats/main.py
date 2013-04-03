import logging
from datetime import datetime

from pylons import c
from allura import model as M
from allura.eventslistener import EventsListener
from model import OrganizationStats
from controllers.organizationstats import ForgeOrgStatsController
from forgeorganizationstats import version
from allura.app import Application, SitemapEntry
from allura.lib import helpers as h

log = logging.getLogger(__name__)

class OrganizationStatsListener(EventsListener):
    def newArtifact(self, art_type, art_datetime, project, user):
        for org in _getInterestedOrganizations(user, project):
            stats = org.stats
            if not stats:
                stats = OrganizationStats.create(org)
            stats.addNewArtifact(art_type, art_datetime, project)

    def modifiedArtifact(self, art_type, art_datetime, project, user):
        for org in _getInterestedOrganizations(user, project):
            stats = org.stats
            if not stats:
                stats = OrganizationStats.create(org)
            stats.addModifiedArtifact(art_type, art_datetime,project)

    def newOrganization(self, organization):
        stats = OrganizationStats.create(organization)

    def newUser(self, user):
        pass

    def ticketEvent(self, event_type, ticket, project, user):
        if user is None:
            return
        organizations = _getInterestedOrganizations(user, project)
        if event_type=="assigned":
            for org in organizations:
                stats = org.stats
                if not stats:
                    stats = OrganizationStats.create(org)
                stats.addAssignedTicket(ticket.mod_date, project)
        elif event_type=="revoked":
            for org in organizations:
                stats = org.stats
                if not stats:
                    stats = OrganizationStats.create(org)
                stats.addRevokedTicket(ticket.mod_date, project)
        elif event_type=="closed":
            for org in organizations:
                stats = org.stats
                if not stats:
                    stats = OrganizationStats.create(org)
                stats.addClosedTicket(ticket.created_date, ticket.mod_date, project)

    def newCommit(self, newcommit, project, user):
        for org in _getInterestedOrganizations(user, project):
            stats = org.stats
            if not stats:
                stats = OrganizationStats.create(org)
            stats.addCommit(newcommit, datetime.utcnow(), project)

    def addUserLogin(self, user):
        pass

def _getInterestedOrganizations(user, project):
    proj_organizations=\
        [org.organization for org in project.organizations
         if org.status=='active']
    return [m.organization for m in user.memberships
            if m.status=='active' and m.organization in proj_organizations]

class ForgeOrganizationStatsApp(Application):
    __version__ = version.__version__
    tool_label='Statistics'
    default_mount_label='Statistics'
    default_mount_point='organizationstats'
    permissions = ['configure', 'read', 'write',
                    'unmoderated_post', 'post', 'moderate', 'admin']
    ordinal=15
    installable=False
    config_options = Application.config_options
    default_external_feeds = []
    icons={
        24:'images/stats_24.png',
        32:'images/stats_32.png',
        48:'images/stats_48.png'
    }
    root = ForgeOrgStatsController()

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_admin, 'admin')]

    def main_menu(self):
        return [SitemapEntry(self.config.options.mount_label.title(), '.')]

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
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
                     'Settings', c.project.url() + 'organizationstats/settings')]
        return links

    def install(self, project):
        #It doesn't make any sense to install the tool twice on the same 
        #project therefore, if it already exists, it doesn't install it
        #a second time.
        for tool in project.app_configs:
            if tool.tool_name == 'organizationstats':
                if self.config.options.mount_point!=tool.options.mount_point:
                    project.uninstall_app(self.config.options.mount_point)
                    return

    def uninstall(self, project):
        pass
