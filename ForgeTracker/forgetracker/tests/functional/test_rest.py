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

from tg import tmpl_context as c

from mock import patch
from tg import config

from allura.lib import helpers as h
from allura.tests import decorators as td
from allura import model as M
from alluratest.controller import TestRestApiBase

from forgetracker import model as TM


class TestTrackerApiBase(TestRestApiBase):

    def setup_method(self, method):
        super().setup_method(method)
        self.setup_with_tools()

    @td.with_tool('test', 'Tickets', 'bugs',
                  TicketMonitoringEmail='test@localhost',
                  TicketMonitoringType='AllTicketChanges')
    def setup_with_tools(self):
        h.set_context('test', 'bugs', neighborhood='Projects')
        self.tracker_globals = c.app.globals

    def create_ticket(self, summary=None, status=None):
        return self.api_post(
            '/rest/p/test/bugs/new',
            wrap_args='ticket_form',
            params=dict(
                summary=summary or 'test new ticket',
                status=self.tracker_globals.open_status_names.split()[0],
                labels='',
                description='',
                assigned_to='',
                **{'custom_fields._milestone': ''}),
            status=status)


class TestRestNewTicket(TestTrackerApiBase):

    def test_new_ticket(self):
        summary = 'test new ticket'
        ticket_view = self.api_post(
            '/rest/p/test/bugs/new',
            wrap_args='ticket_form',
            params=dict(
                summary=summary,
                status=self.tracker_globals.open_status_names.split()[0],
                labels='foo,bar',
                description='descr',
                assigned_to='',
                **{'custom_fields._milestone': ''}
            ))
        json = ticket_view.json['ticket']
        assert json['status'] == 'open', json
        assert json['summary'] == 'test new ticket', json
        assert json['reported_by'] == 'test-admin'
        assert json['labels'] == ['foo', 'bar'], json
        assert json['description'] == 'descr', json
        assert json['private'] is False, json

    def test_invalid_ticket(self):
        self.app.get('/rest/p/test/bugs/2', status=404)

    def test_create_limit(self):
        self.create_ticket(summary='First ticket')
        # Set rate limit to unlimit
        with h.push_config(config, **{'forgetracker.rate_limits': '{}'}):
            summary = 'Second ticket'
            self.create_ticket(summary=summary)
            t = TM.Ticket.query.get(summary=summary)
            assert t is not None
        # Set rate limit to 1 in first hour of project
        with h.push_config(config, **{'forgetracker.rate_limits': '{"3600": 1}'}):
            summary = 'Third ticket'
            self.create_ticket(summary=summary, status=429)
            t = TM.Ticket.query.get(summary=summary)
            assert t is None


class TestRestUpdateTicket(TestTrackerApiBase):

    def setup_method(self, method):
        super().setup_method(method)
        ticket_view = self.create_ticket()
        self.ticket_args = ticket_view.json['ticket']

    def test_update_ticket(self):
        args = dict(self.ticket_args, summary='test update ticket', labels='',
                    assigned_to=self.ticket_args['assigned_to_id'] or '')
        for bad_key in ('ticket_num', 'assigned_to_id', 'created_date',
                        'reported_by', 'reported_by_id', '_id', 'votes_up', 'votes_down', 'discussion_thread'):
            del args[bad_key]
        args['private'] = str(args['private'])
        args['discussion_disabled'] = str(args['discussion_disabled'])
        ticket_view = self.api_post(
            '/rest/p/test/bugs/1/save', wrap_args='ticket_form', params=h.encode_keys(args))
        assert ticket_view.status_int == 200, ticket_view.showbrowser()
        json = ticket_view.json['ticket']
        assert int(json['ticket_num']) == 1
        assert json['summary'] == 'test update ticket', json


class TestRestIndex(TestTrackerApiBase):

    def setup_method(self, method):
        super().setup_method(method)
        self.create_ticket()

    def test_ticket_index(self):
        tickets = self.api_get('/rest/p/test/bugs/')
        assert len(tickets.json['tickets']) == 1, tickets.json
        assert (tickets.json['tickets'][0]
                == dict(ticket_num=1, summary='test new ticket')), tickets.json['tickets'][0]
        assert tickets.json['tracker_config']['options']['mount_point'] == 'bugs'
        assert tickets.json['tracker_config']['options']['TicketMonitoringType'] == 'AllTicketChanges'
        assert tickets.json['tracker_config']['options']['EnableVoting']
        assert tickets.json['tracker_config']['options']['TicketMonitoringEmail'] == 'test@localhost'
        assert tickets.json['tracker_config']['options']['mount_label'] == 'Tickets'
        assert tickets.json['saved_bins'][0]['sort'] == 'mod_date_dt desc'
        assert tickets.json['saved_bins'][0]['terms'] == '!status:closed && !status:wont-fix'
        assert tickets.json['saved_bins'][0]['summary'] == 'Changes'
        assert len(tickets.json['saved_bins'][0]) == 4
        assert tickets.json['milestones'][0]['name'] == '1.0'
        assert tickets.json['milestones'][1]['name'] == '2.0'

    def test_ticket_index_noauth(self):
        tickets = self.api_get('/rest/p/test/bugs', user='*anonymous')
        assert 'TicketMonitoringEmail' not in tickets.json[
            'tracker_config']['options']
        # make sure it didn't get removed from the db too
        ticket_config = M.AppConfig.query.get(
            project_id=c.project._id, tool_name='tickets')
        assert (ticket_config.options.get('TicketMonitoringEmail') ==
                     'test@localhost')

    @td.with_tool('test', 'Tickets', 'dummy')
    def test_move_ticket_redirect(self):
        p = M.Project.query.get(shortname='test')
        dummy_tracker = p.app_instance('dummy')
        self.app.post(
            '/p/test/bugs/1/move',
            params={'tracker': str(dummy_tracker.config._id)}).follow()

        ticket = self.api_get('/rest/p/test/bugs/1/')
        assert ticket.request.path == '/rest/p/test/dummy/1/'


class TestRestDiscussion(TestTrackerApiBase):

    def setup_method(self, method):
        super().setup_method(method)
        ticket_view = self.create_ticket()
        self.ticket_args = ticket_view.json['ticket']

    def test_post(self):
        r = self.api_get('/rest/p/test/bugs/1/')
        thread_id = r.json['ticket']['discussion_thread']['_id']
        post = self.api_post(
            '/rest/p/test/bugs/_discuss/thread/%s/new' % thread_id,
            text='This is a comment', wrap_args=None)
        thread = self.api_get('/rest/p/test/bugs/_discuss/thread/%s/' % thread_id)
        assert len(thread.json['thread']['posts']) == 1, thread.json
        assert post.json['post']['text'] == 'This is a comment', post.json
        reply = self.api_post(
            '/rest/p/test/bugs/_discuss/thread/{}/{}/reply'.format(thread.json['thread']
                                                               ['_id'], post.json['post']['slug']),
            text='This is a reply', wrap_args=None)
        assert reply.json['post']['text'] == 'This is a reply', reply.json
        thread = self.api_get('/rest/p/test/bugs/_discuss/thread/%s/' % thread_id)
        assert len(thread.json['thread']['posts']) == 2, thread.json


class TestRestSearch(TestTrackerApiBase):

    @property
    def ticket(self):
        return TM.Ticket(
            ticket_num=5,
            summary='our test ticket',
            status='open',
            labels=['tiny', 'minor'])

    @patch('forgetracker.model.Ticket.paged_search')
    def test_no_criteria(self, paged_search):
        paged_search.return_value = dict(tickets=[self.ticket])
        r = self.api_get('/rest/p/test/bugs/search')
        assert r.status_int == 200
        assert r.json['tickets'][0]['summary'] == 'our test ticket'
        assert r.json['tickets'][0]['ticket_num'] == 5
        assert r.json['tickets'][0]['status'] == 'open'
        assert r.json['tickets'][0]['labels'] == ['tiny', 'minor']
        assert 'description' not in r.json
        assert 'discussion_thread' not in r.json

    @patch('forgetracker.model.Ticket.paged_search')
    def test_some_criteria(self, paged_search):
        q = 'labels:testing && status:open'
        paged_search.return_value = dict(
            tickets=[self.ticket],
            sort='status',
            limit=2,
            count=1,
            page=0,
            q=q,
        )
        r = self.api_get('/rest/p/test/bugs/search',
                         q=q, sort='status', limit='2')
        assert r.status_int == 200
        assert r.json['limit'] == 2
        assert r.json['q'] == q
        assert r.json['sort'] == 'status'
        assert r.json['count'] == 1
        assert r.json['page'] == 0
        assert r.json['tickets'][0]['summary'] == 'our test ticket'
        assert r.json['tickets'][0]['ticket_num'] == 5
        assert r.json['tickets'][0]['status'] == 'open'
        assert r.json['tickets'][0]['labels'] == ['tiny', 'minor']
        assert 'description' not in r.json
        assert 'discussion_thread' not in r.json


class TestRestHasAccess(TestTrackerApiBase):

    def test_has_access_no_params(self):
        self.api_get('/rest/p/test/bugs/has_access', status=404)
        self.api_get('/rest/p/test/bugs/has_access?user=root', status=404)
        self.api_get('/rest/p/test/bugs/has_access?perm=read', status=404)

    def test_has_access_unknown_params(self):
        """Unknown user and/or permission always False for has_access API"""
        r = self.api_get(
            '/rest/p/test/bugs/has_access?user=babadook&perm=read',
            user='root')
        assert r.status_int == 200
        assert r.json['result'] is False
        r = self.api_get(
            '/rest/p/test/bugs/has_access?user=test-user&perm=jump',
            user='root')
        assert r.status_int == 200
        assert r.json['result'] is False

    def test_has_access_not_admin(self):
        """
        User which has no 'admin' permission on neighborhood can't use
        has_access API
        """
        self.api_get(
            '/rest/p/test/bugs/has_access?user=test-admin&perm=admin',
            user='test-user',
            status=403)

    def test_has_access(self):
        r = self.api_get(
            '/rest/p/test/bugs/has_access?user=test-admin&perm=delete',
            user='root')
        assert r.status_int == 200
        assert r.json['result'] is True
        r = self.api_get(
            '/rest/p/test/bugs/has_access?user=test-user&perm=delete',
            user='root')
        assert r.status_int == 200
        assert r.json['result'] is False
