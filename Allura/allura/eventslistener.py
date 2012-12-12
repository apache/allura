'''This class is supposed to be extended in order to support statistics for
a specific entity (e.g. user, project, ...). To do so, the new classes should
overwrite the methods defined here, which will be called when the related
event happens, so that the statistics for the given entity are updated.'''
class EventsListener:
    def newArtifact(self, art_type, art_datetime, project, user):
        pass

    def modifiedArtifact(self, art_type, art_datetime, project, user):
        pass

    def newUser(self, user):
        pass

    def newOrganization(self, organization):
        pass

    def addUserLogin(self, user):
        pass

    def newCommit(self, newcommit, project, user):
        pass

    def ticketEvent(self, event_type, ticket, project, user):
        pass


