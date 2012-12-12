from tg import expose
from tg.decorators import with_trailing_slash
from datetime import datetime
from allura.controllers import BaseController
import allura.model as M
from allura.lib.graphics.graphic_methods import create_histogram, create_progress_bar
from forgeuserstats.model.stats import UserStats

class ForgeUserStatsController(BaseController):

    @expose()
    def _lookup(self, part, *remainder):
        user = M.User.query.get(username=part)

        if not self.user:
            return ForgeUserStatsController(user=user), remainder
        if part == "category":
            return ForgeUserStatsCatController(self.user, self.stats, None), remainder
        if part == "metric":
            return ForgeUserStatsMetricController(self.user, self.stats), remainder

    def __init__(self, user=None):
        self.user = user
        if self.user:
            self.stats = self.user.stats
            if not self.stats:
                self.stats = UserStats.create(self.user)

        super(ForgeUserStatsController, self).__init__()

    @expose('jinja:forgeuserstats:templates/index.html')
    @with_trailing_slash
    def index(self, **kw):
        if not self.user: 
            return dict(user=None)
        stats = self.stats

        ret_dict = _getDataForCategory(None, stats)
        ret_dict['user'] = self.user

        ret_dict['registration_date'] = stats.registration_date

        ret_dict['totlogins'] = stats.tot_logins_count
        ret_dict['last_login'] = stats.last_login
        if stats.last_login:
            ret_dict['last_login_days'] = \
                (datetime.utcnow()-stats.last_login).days

        categories = {}
        for p in self.user.my_projects():
            for cat in p.trove_topic:
                cat = M.TroveCategory.query.get(_id = cat)
                if categories.get(cat):
                    categories[cat] += 1
                else:
                    categories[cat] = 1
        categories = sorted(categories.items(), key=lambda (x,y): y,reverse=True)

        ret_dict['lastmonth_logins'] = stats.getLastMonthLogins()
        ret_dict['categories'] = categories
        days = ret_dict['days']
        if days >= 30: 
            ret_dict['permonthlogins'] = \
                round(stats.tot_logins_count*30.0/days,2)
        else:
            ret_dict['permonthlogins'] = 'n/a'

        ret_dict['codepercentage'] = stats.codeRanking()
        ret_dict['discussionpercentage'] = stats.discussionRanking()
        ret_dict['ticketspercentage'] = stats.ticketsRanking()
        ret_dict['codecontribution'] = stats.getCodeContribution()
        ret_dict['discussioncontribution'] = stats.getDiscussionContribution()
        ret_dict['ticketcontribution'] = stats.getTicketsContribution()
        ret_dict['maxcodecontrib'], ret_dict['averagecodecontrib'] =\
            stats.getMaxAndAverageCodeContribution()
        ret_dict['maxdisccontrib'], ret_dict['averagedisccontrib'] =\
            stats.getMaxAndAverageDiscussionContribution()
        ret_dict['maxticketcontrib'], ret_dict['averageticketcontrib'] =\
            stats.getMaxAndAverageTicketsSolvingPercentage()

        return ret_dict

    @expose()
    def categories_graph(self):
        categories = {}
        for p in self.user.my_projects():
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
        return create_progress_bar(self.stats.codeRanking())

    @expose()
    def discussion_ranking_bar(self):
        return create_progress_bar(self.stats.discussionRanking())

    @expose()
    def tickets_ranking_bar(self):
        return create_progress_bar(self.stats.ticketsRanking())

class ForgeUserStatsCatController(BaseController):
    @expose()
    def _lookup(self, category, *remainder):
        cat = M.TroveCategory.query.get(fullname=category)
        return ForgeUserStatsCatController(self.user, cat), remainder

    def __init__(self, user, stats, category):
        self.user = user
        self.stats = stats
        self.category = category
        super(ForgeUserStatsCatController, self).__init__()

    @expose('jinja:forgeuserstats:templates/index.html')
    @with_trailing_slash
    def index(self, **kw):
        if not self.user:
            return dict(user=None)
        stats = self.stats
        
        cat_id = None
        if self.category: 
            cat_id = self.category._id
        ret_dict = _getDataForCategory(cat_id, stats)
        ret_dict['user'] = self.user
        ret_dict['registration_date'] = stats.registration_date
        ret_dict['category'] = self.category
        
        return ret_dict

class ForgeUserStatsMetricController(BaseController):

    def __init__(self, user, stats):
        self.user = user
        self.stats = stats
        super(ForgeUserStatsMetricController, self).__init__()

    @expose('jinja:forgeuserstats:templates/commits.html')
    @with_trailing_slash
    def commits(self, **kw):
        if not self.user:
            return dict(user=None)
        stats = self.stats
        
        commits = stats.getCommitsByCategory()
        return dict(user = self.user,
                    data = commits) 

    @expose('jinja:forgeuserstats:templates/artifacts.html')
    @with_trailing_slash
    def artifacts(self, **kw):
        if not self.user:
            return dict(user=None)

        stats = self.stats       
        artifacts = stats.getArtifactsByCategory(detailed=True)
        return dict(user = self.user, data = artifacts) 

    @expose('jinja:forgeuserstats:templates/tickets.html')
    @with_trailing_slash
    def tickets(self, **kw):
        if not self.user: 
            return dict(user=None)

        artifacts = self.stats.getTicketsByCategory()
        return dict(user = self.user, data = artifacts) 

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

