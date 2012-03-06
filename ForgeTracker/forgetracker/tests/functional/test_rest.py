import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pylons import c

from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase


class TestTrackerApiBase(TestRestApiBase):

    def setUp(self):
        super(TestTrackerApiBase, self).setUp()
        self.setup_with_tools()

    @td.with_tracker
    def setup_with_tools(self):
        h.set_context('test', 'bugs', neighborhood='Projects')
        self.tracker_globals = c.app.globals

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
        summary = 'test new ticket'
        ticket_view = self.api_post(
            '/rest/p/test/bugs/new',
            wrap_args='ticket_form',
            summary=summary,
            status=self.tracker_globals.open_status_names.split()[0],
            labels='',
            description='',
            assigned_to='',
            **{'custom_fields._milestone':''})
        self.ticket_args = ticket_view.json['ticket']

    def test_ticket_index(self):
        tickets = self.api_post('/rest/p/test/bugs/')
        assert len(tickets.json['tickets']) == 1, tickets.json
        assert (tickets.json['tickets'][0]
                == dict(ticket_num=1, summary='test new ticket')), tickets.json['tickets'][0]

    def test_update_ticket(self):
        args = dict(self.ticket_args, summary='test update ticket', labels='',
                    assigned_to=self.ticket_args['assigned_to_id'] or '')
        for bad_key in ('ticket_num', 'assigned_to_id', 'created_date', 'reported_by', 'reported_by_id', '_id'):
            del args[bad_key]
        args['private'] = str(args['private'])
        ticket_view = self.api_post('/rest/p/test/bugs/1/save', wrap_args='ticket_form', **h.encode_keys(args))
        assert ticket_view.status_int == 200, ticket_view.showbrowser()
        json = ticket_view.json['ticket']
        assert int(json['ticket_num']) == 1
        assert json['summary'] == 'test update ticket', json

class TestRestDiscussion(TestTrackerApiBase):

    def setUp(self):
        super(TestRestDiscussion, self).setUp()
        summary = 'test new ticket'
        ticket_view = self.api_post(
            '/rest/p/test/bugs/new',
            wrap_args='ticket_form',
            summary=summary,
            status=self.tracker_globals.open_status_names.split()[0],
            labels='',
            description='',
            milestone='',
            assigned_to='')
        self.ticket_args = ticket_view.json['ticket']

    def test_index(self):
        r = self.api_post('/rest/p/test/bugs/_discuss/')
        assert len(r.json['discussion']['threads']) == 1, r.json
        for t in r.json['discussion']['threads']:
            r = self.api_post('/rest/p/test/bugs/_discuss/thread/%s/' % t['_id'])
            assert len(r.json['thread']['posts']) == 0, r.json

    def test_post(self):
        discussion = self.api_post('/rest/p/test/bugs/_discuss/').json['discussion']
        post = self.api_post('/rest/p/test/bugs/_discuss/thread/%s/new' % discussion['threads'][0]['_id'],
                             text='This is a comment', wrap_args=None)
        thread = self.api_post('/rest/p/test/bugs/_discuss/thread/%s/' % discussion['threads'][0]['_id'])
        assert len(thread.json['thread']['posts']) == 1, thread.json
        assert post.json['post']['text'] == 'This is a comment', post.json
        reply = self.api_post(
            '/rest/p/test/bugs/_discuss/thread/%s/%s/reply' % (thread.json['thread']['_id'], post.json['post']['slug']),
            text='This is a reply', wrap_args=None)
        assert reply.json['post']['text'] == 'This is a reply', reply.json
        thread = self.api_post('/rest/p/test/bugs/_discuss/thread/%s/' % discussion['threads'][0]['_id'])
        assert len(thread.json['thread']['posts']) == 2, thread.json
