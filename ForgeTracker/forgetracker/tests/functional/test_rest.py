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

from pylons import tmpl_context as c

from datadiff.tools import assert_equal
from mock import patch

from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase

from forgetracker import model as TM

class TestTrackerApiBase(TestRestApiBase):

    def setUp(self):
        super(TestTrackerApiBase, self).setUp()
        self.setup_with_tools()

    @td.with_tool('test', 'Tickets', 'bugs',
            TicketMonitoringEmail='test@localhost',
            TicketMonitoringType='AllTicketChanges')
    def setup_with_tools(self):
        h.set_context('test', 'bugs', neighborhood='Projects')
        self.tracker_globals = c.app.globals

    def create_ticket(self):
        return self.api_post(
            '/rest/p/test/bugs/new',
            wrap_args='ticket_form',
            summary='test new ticket',
            status=self.tracker_globals.open_status_names.split()[0],
            labels='',
            description='',
            assigned_to='',
            **{'custom_fields._milestone':''})


class TestRestNewTicket(TestTrackerApiBase):

    def test_new_ticket(self):
        summary = 'test new ticket'
        ticket_view = self.api_post(
            '/rest/p/test/bugs/new',
            wrap_args='ticket_form',
            summary=summary,
            status=self.tracker_globals.open_status_names.split()[0],
            labels='foo,bar',
            description='descr',
            assigned_to='',
            **{'custom_fields._milestone':''})
        json = ticket_view.json['ticket']
        assert json['status'] == 'open', json
        assert json['summary'] == 'test new ticket', json
        assert json['reported_by'] == 'test-admin'
        assert json['labels'] == ['foo', 'bar'], json
        assert json['description'] == 'descr', json
        assert json['private'] == False, json

    def test_invalid_ticket(self):
        self.app.get('/rest/p/test/bugs/2', status=404)

class TestRestUpdateTicket(TestTrackerApiBase):

    def setUp(self):
        super(TestRestUpdateTicket, self).setUp()
        ticket_view = self.create_ticket()
        self.ticket_args = ticket_view.json['ticket']

    def test_update_ticket(self):
        args = dict(self.ticket_args, summary='test update ticket', labels='',
                    assigned_to=self.ticket_args['assigned_to_id'] or '')
        for bad_key in ('ticket_num', 'assigned_to_id', 'created_date',
                'reported_by', 'reported_by_id', '_id', 'votes_up', 'votes_down'):
            del args[bad_key]
        args['private'] = str(args['private'])
        ticket_view = self.api_post('/rest/p/test/bugs/1/save', wrap_args='ticket_form', **h.encode_keys(args))
        assert ticket_view.status_int == 200, ticket_view.showbrowser()
        json = ticket_view.json['ticket']
        assert int(json['ticket_num']) == 1
        assert json['summary'] == 'test update ticket', json


class TestRestIndex(TestTrackerApiBase):

    def setUp(self):
        super(TestRestIndex, self).setUp()
        self.create_ticket()

    def test_ticket_index(self):
        tickets = self.api_get('/rest/p/test/bugs/')
        assert len(tickets.json['tickets']) == 1, tickets.json
        assert (tickets.json['tickets'][0]
                == dict(ticket_num=1, summary='test new ticket')), tickets.json['tickets'][0]
        assert tickets.json['tracker_config']['options']['mount_point'] == 'bugs'
        assert tickets.json['tracker_config']['options']['TicketMonitoringType'] == 'AllTicketChanges'
        assert not tickets.json['tracker_config']['options']['EnableVoting']
        assert tickets.json['tracker_config']['options']['TicketMonitoringEmail'] == 'test@localhost'
        assert tickets.json['tracker_config']['options']['mount_label'] == 'Tickets'
        assert tickets.json['saved_bins'][0]['sort'] == 'mod_date_dt desc'
        assert tickets.json['saved_bins'][0]['terms'] == '!status:wont-fix && !status:closed'
        assert tickets.json['saved_bins'][0]['summary'] == 'Changes'
        assert len(tickets.json['saved_bins'][0]) == 4
        assert tickets.json['milestones'][0]['name'] == '1.0'
        assert tickets.json['milestones'][1]['name'] == '2.0'

    def test_ticket_index_noauth(self):
        tickets = self.api_get('/rest/p/test/bugs', user='*anonymous')
        assert 'TicketMonitoringEmail' not in tickets.json['tracker_config']['options']


class TestRestDiscussion(TestTrackerApiBase):

    def setUp(self):
        super(TestRestDiscussion, self).setUp()
        ticket_view = self.create_ticket()
        self.ticket_args = ticket_view.json['ticket']

    def test_index(self):
        r = self.api_get('/rest/p/test/bugs/_discuss/')
        assert len(r.json['discussion']['threads']) == 1, r.json
        for t in r.json['discussion']['threads']:
            r = self.api_get('/rest/p/test/bugs/_discuss/thread/%s/' % t['_id'])
            assert len(r.json['thread']['posts']) == 0, r.json

    def test_post(self):
        discussion = self.api_get('/rest/p/test/bugs/_discuss/').json['discussion']
        post = self.api_post('/rest/p/test/bugs/_discuss/thread/%s/new' % discussion['threads'][0]['_id'],
                             text='This is a comment', wrap_args=None)
        thread = self.api_get('/rest/p/test/bugs/_discuss/thread/%s/' % discussion['threads'][0]['_id'])
        assert len(thread.json['thread']['posts']) == 1, thread.json
        assert post.json['post']['text'] == 'This is a comment', post.json
        reply = self.api_post(
            '/rest/p/test/bugs/_discuss/thread/%s/%s/reply' % (thread.json['thread']['_id'], post.json['post']['slug']),
            text='This is a reply', wrap_args=None)
        assert reply.json['post']['text'] == 'This is a reply', reply.json
        thread = self.api_get('/rest/p/test/bugs/_discuss/thread/%s/' % discussion['threads'][0]['_id'])
        assert len(thread.json['thread']['posts']) == 2, thread.json

class TestRestSearch(TestTrackerApiBase):

    @patch('forgetracker.model.Ticket.paged_search')
    def test_no_criteria(self, paged_search):
        paged_search.return_value = dict(tickets=[
            TM.Ticket(ticket_num=5, summary='our test ticket'),
        ])
        r = self.api_get('/rest/p/test/bugs/search')
        assert_equal(r.status_int, 200)
        assert_equal(r.json, {'tickets':[
            {'summary': 'our test ticket', 'ticket_num': 5},
        ]})

    @patch('forgetracker.model.Ticket.paged_search')
    def test_some_criteria(self, paged_search):
        q = 'labels:testing && status:open'
        paged_search.return_value = dict(tickets=[
                TM.Ticket(ticket_num=5, summary='our test ticket'),
            ],
            sort='status',
            limit=2,
            count=1,
            page=0,
            q=q,
        )
        r = self.api_get('/rest/p/test/bugs/search', q=q, sort='status', limit='2')
        assert_equal(r.status_int, 200)
        assert_equal(r.json, {'limit': 2, 'q': q, 'sort':'status', 'count': 1,
                               'page': 0, 'tickets':[
                {'summary': 'our test ticket', 'ticket_num': 5},
            ]
        })
