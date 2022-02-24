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
from datetime import datetime
import re

from tg import expose, validate, redirect
from tg.decorators import with_trailing_slash
from tg import tmpl_context as c
from webob import exc

from allura.controllers import BaseController
import allura.model as M
from allura.lib.security import require_access
from allura.lib.decorators import require_post

from forgeuserstats.model.stats import UserStats
from forgeuserstats.widgets.forms import StatsPreferencesForm


stats_preferences_form = StatsPreferencesForm()


class ForgeUserStatsCatController(BaseController):

    @expose()
    def _lookup(self, category, *remainder):
        cat = M.TroveCategory.query.get(shortname=category, fullpath=re.compile(r'^Topic :: '))
        if not cat:
            raise exc.HTTPNotFound
        return ForgeUserStatsCatController(category=cat), remainder

    def __init__(self, category=None):
        self.category = category
        super().__init__()

    @expose('jinja:forgeuserstats:templates/index.html')
    @with_trailing_slash
    def index(self, **kw):
        self.user = c.project.user_project_of
        if not self.user:
            return None
        stats = self.user.stats
        if (not stats.visible) and (c.user != self.user):
            return dict(user=self.user)

        cat_id = None
        if self.category:
            cat_id = self.category._id
        ret_dict = _getDataForCategory(cat_id, stats)
        ret_dict['user'] = self.user
        ret_dict['registration_date'] = stats.registration_date
        ret_dict['category'] = self.category
        return ret_dict


class ForgeUserStatsController(BaseController):

    category = ForgeUserStatsCatController()

    @expose('jinja:forgeuserstats:templates/settings.html')
    @with_trailing_slash
    def settings(self, **kw):
        require_access(c.project, 'admin')

        self.user = c.project.user_project_of
        if not self.user:
            return dict(user=None)
        if not self.user.stats:
            UserStats.create(self.user)
        return dict(
            user=self.user,
            form=StatsPreferencesForm(
                action=c.project.url() + 'userstats/change_settings'))

    @expose()
    @require_post()
    @validate(stats_preferences_form, error_handler=settings)
    def change_settings(self, **kw):
        require_access(c.project, 'admin')

        self.user = c.project.user_project_of
        if not self.user:
            return dict(user=None)
        if not self.user.stats:
            UserStats.create(self.user)
        visible = kw.get('visible')
        self.user.stats.visible = visible
        redirect(c.project.url() + 'userstats/settings')

    @expose('jinja:forgeuserstats:templates/index.html')
    @with_trailing_slash
    def index(self, **kw):
        self.user = c.project.user_project_of
        if not self.user:
            return dict(user=None)
        if not self.user.stats:
            UserStats.create(self.user)

        stats = self.user.stats
        if (not stats.visible) and (c.user != self.user):
            return dict(user=self.user)

        ret_dict = _getDataForCategory(None, stats)
        ret_dict['user'] = self.user

        ret_dict['registration_date'] = stats.registration_date

        ret_dict['totlogins'] = stats.tot_logins_count
        ret_dict['last_login'] = stats.last_login
        if stats.last_login:
            ret_dict['last_login_days'] = \
                (datetime.utcnow() - stats.last_login).days

        categories = {}
        for p in self.user.my_projects():
            for cat in p.trove_topic:
                cat = M.TroveCategory.query.get(_id=cat)
                if categories.get(cat):
                    categories[cat] += 1
                else:
                    categories[cat] = 1
        categories = sorted(list(categories.items()),
                            key=lambda x_y: x_y[1], reverse=True)

        ret_dict['lastmonth_logins'] = stats.getLastMonthLogins()
        ret_dict['categories'] = categories
        days = ret_dict['days']
        if days >= 30:
            ret_dict['permonthlogins'] = \
                round(stats.tot_logins_count * 30.0 / days, 2)
        else:
            ret_dict['permonthlogins'] = 'n/a'

        return ret_dict

    @expose('jinja:forgeuserstats:templates/commits.html')
    @with_trailing_slash
    def commits(self, **kw):
        self.user = c.project.user_project_of
        if not self.user:
            return dict(user=None)
        if not self.user.stats:
            UserStats.create(self.user)
        stats = self.user.stats

        if (not stats.visible) and (c.user != self.user):
            return dict(user=self.user)

        commits = stats.getCommitsByCategory()
        return dict(
            user=self.user,
            data=commits)

    @expose('jinja:forgeuserstats:templates/artifacts.html')
    @with_trailing_slash
    def artifacts(self, **kw):
        self.user = c.project.user_project_of
        if not self.user:
            return dict(user=None)
        if not self.user.stats:
            UserStats.create(self.user)
        stats = self.user.stats

        if (not stats.visible) and (c.user != self.user):
            return dict(user=self.user)

        stats = self.user.stats
        artifacts = stats.getArtifactsByCategory(detailed=True)
        return dict(
            user=self.user,
            data=artifacts)

    @expose('jinja:forgeuserstats:templates/tickets.html')
    @with_trailing_slash
    def tickets(self, **kw):
        self.user = c.project.user_project_of
        if not self.user:
            return dict(user=None)
        if not self.user.stats:
            UserStats.create(self.user)
        stats = self.user.stats

        if (not stats.visible) and (c.user != self.user):
            return dict(user=self.user)

        artifacts = self.user.stats.getTicketsByCategory()
        return dict(
            user=self.user,
            data=artifacts)


def _getDataForCategory(category, stats):
    totcommits = stats.getCommits(category)
    tottickets = stats.getTickets(category)
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

    days = (datetime.utcnow() - stats.start_date).days
    if days >= 30:
        pmartifacts = dict(
            created=round(totartifacts['created'] * 30.0 / days, 2),
            modified=round(totartifacts['modified'] * 30.0 / days, 2))
        pmcommits = dict(
            number=round(totcommits['number'] * 30.0 / days, 2),
            lines=round(totcommits['lines'] * 30.0 / days, 2))
        pmtickets = dict(
            assigned=round(tottickets['assigned'] * 30.0 / days, 2),
            revoked=round(tottickets['revoked'] * 30.0 / days, 2),
            solved=round(tottickets['solved'] * 30.0 / days, 2),
            averagesolvingtime='n/a')
        for key in artifacts_by_type:
            value = artifacts_by_type[key]
            artifacts_by_type[key]['pmcreated'] = \
                round(value['created'] * 30.0 / days, 2)
            artifacts_by_type[key]['pmmodified'] = \
                round(value['modified'] * 30.0 / days, 2)
    else:
        pmartifacts = dict(created='n/a', modified='n/a')
        pmcommits = dict(number='n/a', lines='n/a')
        pmtickets = dict(
            assigned='n/a',
            revoked='n/a',
            solved='n/a',
            averagesolvingtime='n/a')
        for key in artifacts_by_type:
            artifacts_by_type[key]['pmcreated'] = 'n/a'
            artifacts_by_type[key]['pmmodified'] = 'n/a'

    return dict(
        days=days,
        totcommits=totcommits,
        lastmonthcommits=lmcommits,
        lastmonthtickets=lm_tickets,
        tottickets=tottickets,
        permonthcommits=pmcommits,
        totartifacts=totartifacts,
        lastmonthartifacts=lm_totartifacts,
        permonthartifacts=pmartifacts,
        artifacts_by_type=artifacts_by_type,
        lastmonth_artifacts_by_type=lm_artifacts_by_type,
        permonthtickets=pmtickets)
