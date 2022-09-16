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

import pkg_resources
import unittest

from tg import tmpl_context as c

from alluratest.controller import TestController, setup_basic_test, setup_global_objects
from allura.tests import decorators as td
from allura.lib import helpers as h
from allura.model import User
from allura import model as M

from forgetracker import model as TM


class TestStats(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        p = M.Project.query.get(shortname='test')
        p.add_user(M.User.by_username('test-user'), ['Admin'])

    def test_login(self):
        user = User.by_username('test-user')
        init_logins = user.stats.tot_logins_count
        self.app.get('/').follow()  # establish session
        self.app.post('/auth/do_login', antispam=True, params=dict(
            username=user.username, password='foo',
            _session_id=self.app.cookies['_session_id'],
        ))

        assert user.stats.tot_logins_count == 1 + init_logins
        assert user.stats.getLastMonthLogins() == 1 + init_logins

    @td.with_user_project('test-admin')
    @td.with_tool('test', 'wiki', mount_point='wiki', mount_label='wiki', username='test-admin')
    def test_wiki_stats(self):
        initial_artifacts = c.user.stats.getArtifacts()
        initial_wiki = c.user.stats.getArtifacts(art_type="Wiki")
        self.app.post('/wiki/TestPage/update',
                      params=dict(title='TestPage', text='some text'),
                      extra_environ=dict(username=str(c.user.username)))

        artifacts = c.user.stats.getArtifacts()
        wiki = c.user.stats.getArtifacts(art_type="Wiki")

        assert artifacts['created'] == 1 + initial_artifacts['created']
        assert artifacts['modified'] == initial_artifacts['modified']
        assert wiki['created'] == 1 + initial_wiki['created']
        assert wiki['modified'] == initial_wiki['modified']

        self.app.post('/wiki/TestPage2/update',
                      params=dict(title='TestPage2', text='some text'),
                      extra_environ=dict(username=str(c.user.username)))

        artifacts = c.user.stats.getArtifacts()
        wiki = c.user.stats.getArtifacts(art_type="Wiki")

        assert artifacts['created'] == 2 + initial_artifacts['created']
        assert artifacts['modified'] == initial_artifacts['modified']
        assert wiki['created'] == 2 + initial_wiki['created']
        assert wiki['modified'] == initial_wiki['modified']

        self.app.post('/wiki/TestPage2/update',
                      params=dict(title='TestPage2',
                                  text='some modified text'),
                      extra_environ=dict(username=str(c.user.username)))

        artifacts = c.user.stats.getArtifacts()
        wiki = c.user.stats.getArtifacts(art_type="Wiki")

        assert artifacts['created'] == 2 + initial_artifacts['created']
        assert artifacts['modified'] == 1 + initial_artifacts['modified']
        assert wiki['created'] == 2 + initial_wiki['created']
        assert wiki['modified'] == 1 + initial_wiki['modified']

    @td.with_tool('test', 'tickets', mount_point='tickets', mount_label='tickets', username='test-admin')
    def test_tracker_stats(self):
        initial_tickets = c.user.stats.getTickets()
        initial_tickets_artifacts = c.user.stats.getArtifacts(
            art_type="Ticket")

        self.app.post('/tickets/save_ticket',
                      params={'ticket_form.summary': 'test',
                              'ticket_form.assigned_to': str(c.user.username)},
                      extra_environ=dict(username=str(c.user.username)))

        ticketnum = str(TM.Ticket.query.get(summary='test').ticket_num)

        tickets = c.user.stats.getTickets()
        tickets_artifacts = c.user.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 1
        assert tickets['solved'] == initial_tickets['solved']
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts[
            'created'] == initial_tickets_artifacts['created'] + 1
        assert tickets_artifacts[
            'modified'] == initial_tickets_artifacts['modified']

        self.app.post('/tickets/%s/update_ticket_from_widget' % ticketnum,
                      params={'ticket_form.ticket_num': ticketnum,
                              'ticket_form.summary': 'footext3',
                              'ticket_form.status': 'closed'},
                      extra_environ=dict(username=str(c.user.username)))

        tickets = c.user.stats.getTickets()
        tickets_artifacts = c.user.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 1
        assert tickets['solved'] == initial_tickets['solved'] + 1
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts[
            'created'] == initial_tickets_artifacts['created'] + 1
        assert tickets_artifacts[
            'modified'] == initial_tickets_artifacts['modified'] + 1

        self.app.post('/tickets/save_ticket',
                      params={'ticket_form.summary': 'test2'},
                      extra_environ=dict(username=str(c.user.username)))

        ticketnum = str(TM.Ticket.query.get(summary='test2').ticket_num)

        tickets = c.user.stats.getTickets()
        tickets_artifacts = c.user.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 1
        assert tickets['solved'] == initial_tickets['solved'] + 1
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts[
            'created'] == initial_tickets_artifacts['created'] + 2
        assert tickets_artifacts[
            'modified'] == initial_tickets_artifacts['modified'] + 1

        self.app.post('/tickets/%s/update_ticket_from_widget' % ticketnum,
                      params={'ticket_form.ticket_num': ticketnum,
                              'ticket_form.summary': 'test2',
                              'ticket_form.assigned_to': str(c.user.username)},
                      extra_environ=dict(username=str(c.user.username)))

        tickets = c.user.stats.getTickets()
        tickets_artifacts = c.user.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 2
        assert tickets['solved'] == initial_tickets['solved'] + 1
        assert tickets['revoked'] == initial_tickets['revoked']
        assert tickets_artifacts[
            'created'] == initial_tickets_artifacts['created'] + 2
        assert tickets_artifacts[
            'modified'] == initial_tickets_artifacts['modified'] + 2

        self.app.post('/tickets/%s/update_ticket_from_widget' % ticketnum,
                      params={'ticket_form.ticket_num': ticketnum,
                              'ticket_form.summary': 'test2',
                              'ticket_form.assigned_to': 'test-user'},
                      extra_environ=dict(username=str(c.user.username)))

        tickets = c.user.stats.getTickets()
        tickets_artifacts = c.user.stats.getArtifacts(art_type="Ticket")

        assert tickets['assigned'] == initial_tickets['assigned'] + 2
        assert tickets['solved'] == initial_tickets['solved'] + 1
        assert tickets['revoked'] == initial_tickets['revoked'] + 1
        assert tickets_artifacts[
            'created'] == initial_tickets_artifacts['created'] + 2
        assert tickets_artifacts[
            'modified'] == initial_tickets_artifacts['modified'] + 3


class TestGitCommit(TestController, unittest.TestCase):

    def setup_method(self, method):
        super().setup_method(method)
        setup_basic_test()

        user = User.by_username('test-admin')
        user.set_password('testpassword')
        user.claim_address('rcopeland@geek.net')
        addr = M.EmailAddress.get(email='rcopeland@geek.net')
        addr.confirmed = True
        self.setup_with_tools()

    @td.with_tool('test', 'Git', 'git-userstats-stats', 'Git', type='git')
    @td.with_wiki
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'git-userstats-stats', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename(
            'forgeuserstats', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.name = 'testgit.git'
        self.repo = c.app.repo
        self.repo.refresh()
        self.rev = self.repo.commit('HEAD')

    @td.with_user_project('test-admin')
    def test_commit(self):
        commits = c.user.stats.getCommits()
        assert commits['number'] == 4
        lmcommits = c.user.stats.getLastMonthCommits()
        assert lmcommits['number'] == 4
