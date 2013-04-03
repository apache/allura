from ming.orm import FieldProperty
from ming import schema as S
from datetime import datetime, timedelta
from ming.orm import session, Mapper

from allura.model.session import main_orm_session

from allura.model import Stats

class OrganizationStats(Stats):
    class __mongometa__:
        name='organizationstats'
        session = main_orm_session
        unique_indexes = [ '_id', 'organization_id']

    organization_id = FieldProperty(S.ObjectId)

    @classmethod
    def create(cls, organization):
        stats = cls(organization_id=organization._id,
            registration_date = datetime.utcnow())
        organization.stats_id = stats._id
        return stats

    def getLastMonthCommitsPerMember(self, category = None):
        from forgeorganization.organization.model import Organization

        org = Organization.query.get(_id=self.organization_id)
        members = len(org.getEnrolledUsers())
        if not members: 
            return dict(number=0.0, lines=0.0)
        commits = self.getLastMonthCommits(category=category)
        return dict(
            number=round(float(commits['number'])/members,2), 
            lines=round(float(commits['lines'])/members,2))

    def getLastMonthArtifactsPerMember(self, category = None, art_type = None):
        from forgeorganization.organization.model import Organization

        org = Organization.query.get(_id=self.organization_id)
        members = len(org.getEnrolledUsers())
        if not members: 
            return dict(number=0.0, lines=0.0)
        artifacts = self.getLastMonthArtifacts(category=category)
        return dict(
            created=round(float(artifacts['created'])/members,2), 
            modified=round(float(artifacts['modified'])/members,2))

    def getLastMonthTicketsPerMember(self, category = None):
        from forgeorganization.organization.model import Organization

        org = Organization.query.get(_id=self.organization_id)
        members = len(org.getEnrolledUsers())
        if not members: 
            return dict(number=0.0, lines=0.0)
        tickets = self.getLastMonthTickets(category=category)
        return dict(
            assigned=round(float(tickets['assigned'])/members,2), 
            solved=round(float(tickets['solved'])/members,2), 
            revoked=round(float(tickets['revoked'])/members,2))

Mapper.compile_all()
