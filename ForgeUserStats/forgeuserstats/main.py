import logging
from datetime import datetime

from allura.eventslistener import EventsListener
from model.stats import UserStats
from controllers.userstats import ForgeUserStatsController

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
            stats.addAssignedTicket(ticket, project)
        elif event_type == "revoked":
            stats.addRevokedTicket(ticket, project)
        elif event_type == "closed":
            stats.addClosedTicket(ticket, project)

    def newCommit(self, newcommit, project, user):
        stats = user.stats
        if not stats:
            stats = UserStats.create(user)

        stats.addCommit(newcommit, project)

    def addUserLogin(self, user):
        stats = user.stats
        if not stats:
            stats = UserStats.create(user)

        stats.addLogin()

    def newOrganization(self, organization):
        pass

class ForgeUserStatsApp:
    root = ForgeUserStatsController()
    listener = UserStatsListener()

    @classmethod
    def createlink(cls, user):
        return (
            "/userstats/%s/" % user.username, 
            "%s personal statistcs" % user.display_name)
