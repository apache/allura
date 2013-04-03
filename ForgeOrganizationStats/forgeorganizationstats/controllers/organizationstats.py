from pylons import c
from tg import expose, validate, redirect
from tg.decorators import with_trailing_slash
from datetime import datetime, timedelta
from allura.controllers import BaseController
import allura.model as M
from forgeorganization.organization.model import Organization
from forgeorganizationstats.model import OrganizationStats
from allura.lib.graphics.graphic_methods import create_histogram, create_progress_bar
from forgeorganizationstats.widgets.forms import StatsPreferencesForm
from allura.lib.decorators import require_post
from allura.lib.security import require_access
from allura.lib import validators as V

stats_preferences_form = StatsPreferencesForm()

class ForgeOrgStatsCatController(BaseController):
    @expose()
    def _lookup(self, category, *remainder):
        cat = M.TroveCategory.query.get(shortname=category)
        return ForgeOrgStatsCatController(self.organization, cat), remainder

    def __init__(self, category=None):
        self.category = category
        super(ForgeOrgStatsCatController, self).__init__()

    @expose('jinja:forgeorganizationstats:templates/index.html')
    @with_trailing_slash
    def index(self, **kw):
        self.organization = c.project.organization_project_of
        if not self.organization: 
            return None
        stats = self.organization.stats
        if not stats: 
            stats = OrganizationStats.create(self.organization)
        if (not stats.visible) and (c.user.username not in c.project.admins()):
            return dict(organization=self.organization)
        
        cat_id = None
        if self.category: 
            cat_id = self.category._id
        ret_dict = _getDataForCategory(cat_id, self.organization.stats)
        ret_dict['organization'] = self.organization
        ret_dict['registration_date'] = stats.registration_date
        ret_dict['category'] = self.category
        
        return ret_dict

class ForgeOrgStatsController(BaseController):

    category = ForgeOrgStatsCatController()

    @expose('jinja:forgeorganizationstats:templates/index.html')
    @with_trailing_slash
    def index(self, **kw):
        self.organization = c.project.organization_project_of
        if not self.organization: 
            return dict(organization=None)
        stats = self.organization.stats
        if not stats:
            stats = OrganizationStats.create(self.organization)

        if (not stats.visible) and (not (c.user.username in c.project.admins())):
            return dict(organization=self.organization)

        ret_dict = _getDataForCategory(None, stats)
        ret_dict['organization'] = self.organization

        ret_dict['registration_date'] = stats.registration_date

        categories = {}
        for el in self.organization.project_involvements:
            if el.status == 'active':
                p = el.project
                for cat in p.trove_topic:
                    cat = M.TroveCategory.query.get(_id = cat)
                    if categories.get(cat):
                        categories[cat] += 1
                    else:
                        categories[cat] = 1
        categories = sorted(
            categories.items(), 
            key=lambda (x,y): y,
            reverse=True)

        ret_dict['maxcodecontrib'], ret_dict['averagecodecontrib'] =\
            stats.getMaxAndAverageCodeContribution()
        ret_dict['maxdisccontrib'], ret_dict['averagedisccontrib'] =\
            stats.getMaxAndAverageDiscussionContribution()
        ret_dict['maxticketcontrib'], ret_dict['averageticketcontrib'] =\
            stats.getMaxAndAverageTicketsSolvingPercentage()
        members = [m for m in self.organization.memberships 
                   if m.status=='active']
        now = datetime.utcnow()
        newmembers = [m for m in self.organization.memberships
                      if m.startdate and now - m.startdate < timedelta(30)]
        leftmembers = [m for m in self.organization.memberships
                       if m.closeddate and now - m.closeddate < timedelta(30)]
        new_cooperations = [p for p in self.organization.project_involvements
            if p.startdate and now - p.startdate < timedelta(30) and 
               p.collaborationtype=='cooperation']
        new_participations = [p for p in self.organization.project_involvements
            if p.startdate and now - p.startdate < timedelta(30) and 
               p.collaborationtype=='participation']
        old_cooperations = [p for p in self.organization.project_involvements
            if p.closeddate and now - p.closeddate < timedelta(30) and 
               p.collaborationtype=='cooperation']
        old_participations = [p for p in self.organization.project_involvements
            if p.closeddate and now - p.closeddate < timedelta(30) and 
               p.collaborationtype=='participation']

        return dict(
            ret_dict,
            categories = categories,
            codepercentage = stats.codeRanking(),
            discussionpercentage = stats.discussionRanking(),
            ticketspercentage = stats.ticketsRanking(),
            codecontribution = stats.getCodeContribution(),
            discussioncontribution = stats.getDiscussionContribution(),
            ticketcontribution = stats.getTicketsContribution(),
            membersnumber = len(members),
            newmembers = len(newmembers),
            leftmembers = len(leftmembers),
            coopnumber=len(self.organization.getActiveCooperations()),
            participnumber = len(self.organization.getActiveParticipations()),
            newcooperations = len(new_cooperations),
            newparticipations = len(new_participations),
            oldcooperations = len(old_cooperations),
            oldparticipations = len(old_participations),
            permemberartifacts = stats.getLastMonthArtifactsPerMember(),
            permembertickets = stats.getLastMonthTicketsPerMember(),
            permembercommits = stats.getLastMonthCommitsPerMember())

    @expose()
    def categories_graph(self):
        categories = {}
        for el in self.organization.project_involvements:
            if el.status == 'active':
                p = el.project
                for cat in p.trove_topic:
                    cat = M.TroveCategory.query.get(_id = cat)
                    if categories.get(cat):
                        categories[cat] += 1
                    else:
                        categories[cat] = 1
        data = []
        labels = []
        i = 0
        for cat in sorted(categories.keys(), key=lambda x:x.fullname):
            n = categories[cat]
            data = data + [i] * n
            label = cat.fullname
            if len(label) > 15:
                label = label[:15] + "..."
            labels.append(label)
            i += 1

        return create_histogram(data, labels, 
            'Number of projects', 'Projects by category')

    @expose()
    def code_ranking_bar(self):
        return create_progress_bar(self.organization.stats.codeRanking())

    @expose()
    def discussion_ranking_bar(self):
        return create_progress_bar(self.organization.stats.discussionRanking())

    @expose()
    def tickets_ranking_bar(self):
        return create_progress_bar(self.organization.stats.ticketsRanking())

    @expose('jinja:forgeorganizationstats:templates/commits.html')
    @with_trailing_slash
    def commits(self, **kw):
        self.organization = c.project.organization_project_of
        if not self.organization: 
            return None
        stats = self.organization.stats
        if not stats: 
            stats = OrganizationStats.create(self.organization)
        if (not stats.visible) and (c.user.username not in c.project.admins()):
            return dict(organization=self.organization)
        
        commits = stats.getCommitsByCategory()
        return dict(organization = self.organization,
                    data = commits) 

    @expose('jinja:forgeorganizationstats:templates/artifacts.html')
    @with_trailing_slash
    def artifacts(self, **kw):
        self.organization = c.project.organization_project_of
        if not self.organization: 
            return None
        stats = self.organization.stats
        if not stats: 
            stats = OrganizationStats.create(self.organization)
        if (not stats.visible) and (c.user.username not in c.project.admins()):
            return dict(organization=self.organization)

        artifacts = stats.getArtifactsByCategory(detailed=True)
        return dict(organization = self.organization, data = artifacts) 

    @expose('jinja:forgeorganizationstats:templates/tickets.html')
    @with_trailing_slash
    def tickets(self, **kw):
        self.organization = c.project.organization_project_of
        if not self.organization: 
            return None
        stats = self.organization.stats
        if not stats: 
            stats = OrganizationStats.create(self.organization)
        if (not stats.visible) and (c.user.username not in c.project.admins()):
            return dict(organization=self.organization)

        artifacts = stats.getTicketsByCategory()
        return dict(organization= self.organization, data = artifacts) 

    @expose('jinja:forgeorganizationstats:templates/settings.html')
    @with_trailing_slash
    def settings(self, **kw):
        require_access(c.project, 'admin')

        self.organization = c.project.organization_project_of
        if not self.organization: 
            return dict(organization=None)
        if not self.organization.stats:
            OrganizationStats.create(self.organization)
        return dict(
            organization = self.organization, 
            form = StatsPreferencesForm(
                action = c.project.url() + 'organizationstats/change_settings'))

    @expose()
    @require_post()
    @validate(stats_preferences_form, error_handler=settings)
    def change_settings(self, **kw):
        require_access(c.project, 'admin')

        self.organization = c.project.organization_project_of
        if not self.organization: 
            return dict(organization=None)
        if not self.organization.stats:
            OrganizationStats.create(self.organization)
        visible = kw.get('visible')
        self.organization.stats.visible = visible
        redirect(c.project.url() + 'organizationstats/settings')

def _getDataForCategory(category, stats):
    totcommits = stats.getCommits(category)
    tottickets = stats.getTickets(category)
    averagetime = tottickets.get('averagesolvingtime')
    artifacts_by_type = stats.getArtifactsByType(category)
    totartifacts = artifacts_by_type.get(None) 
    if totartifacts:
        del artifacts_by_type[None]
    else:
        totartifacts = dict(created=0, modified=0)
    lmcommits = stats.getLastMonthCommits(category)
    lm_artifacts_by_type = stats.getLastMonthArtifactsByType(category)
    lm_totartifacts = stats.getLastMonthArtifacts(category)
    lm_tickets = stats.getLastMonthTickets(category)

    averagetime = lm_tickets.get('averagesolvingtime')

    days = (datetime.utcnow() - stats.registration_date).days
    if days >= 30: 
        pmartifacts = dict(
            created = round(totartifacts['created']*30.0/days,2),
            modified=round(totartifacts['modified']*30.0/days,2))
        pmcommits = dict(
            number=round(totcommits['number']*30.0/days,2),
            lines=round(totcommits['lines']*30.0/days,2))
        pmtickets = dict(
            assigned=round(tottickets['assigned']*30.0/days,2),
            revoked=round(tottickets['revoked']*30.0/days,2),
            solved=round(tottickets['solved']*30.0/days,2),
            averagesolvingtime='n/a')
        for key in artifacts_by_type:
            value = artifacts_by_type[key]
            artifacts_by_type[key]['pmcreated'] = \
                round(value['created']*30.0/days,2)
            artifacts_by_type[key]['pmmodified']= \
                round(value['modified']*30.0/days,2)
    else: 
        pmartifacts = dict(created='n/a', modified='n/a')
        pmcommits = dict(number='n/a', lines='n/a')
        pmtickets = dict(
            assigned='n/a',
            revoked='n/a',
            solved='n/a',
            averagesolvingtime='n/a')
        for key in artifacts_by_type:
            value = artifacts_by_type[key]
            artifacts_by_type[key]['pmcreated'] = 'n/a'
            artifacts_by_type[key]['pmmodified']= 'n/a'

    return dict(
        days = days,
        totcommits = totcommits,
        lastmonthcommits = lmcommits,
        lastmonthtickets = lm_tickets,
        tottickets = tottickets,
        permonthcommits = pmcommits,
        totartifacts = totartifacts,
        lastmonthartifacts = lm_totartifacts,
        permonthartifacts = pmartifacts,
        artifacts_by_type = artifacts_by_type,
        lastmonth_artifacts_by_type = lm_artifacts_by_type,
        permonthtickets = pmtickets)

