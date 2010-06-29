from pprint import pprint
from datetime import datetime, timedelta
from formencode import variabledecode
import json

from ming.orm import session

from pyforge import model as M
from pyforge.lib import helpers as h
from pyforge.tests import helpers

from forgetracker.tests import TestController
from forgetracker import model as TM

class TestRestApiBase(TestController):

    def setUp(self):
        super(TestRestApiBase, self).setUp()
        helpers.setup_global_objects()
        h.set_context('test', 'bugs')
        user = M.User.query.get(username='test-admin')
        self.token = M.ApiToken(user_id=user._id)
        self.tracker_globals = TM.Globals.for_current_tracker()
        session(self.token).flush()
        self.mount_point = '/rest/p/test/bugs/'

    def api_post(self, path, api_key=None, api_timestamp=None, api_signature=None,
                 wrap_args='ticket_form', **ticket_form):
        if wrap_args:
            params = { wrap_args: json.dumps(ticket_form) }
        else:
            params = dict(ticket_form)
        params = variabledecode.variable_encode(params, add_repetitions=False)
        if api_key: params['api_key'] = api_key
        if api_timestamp: params['api_timestamp'] = api_timestamp
        if api_signature: params['api_signature'] = api_signature
        path = self.mount_point + path
        params = self.token.sign_request(path, params)
        response = self.app.post(
            str(path),
            params=params,
            status=[200,302,400,403])
        if response.status_int == 302:
            return response.follow()
        else:
            return response

class TestRestNewTicket(TestRestApiBase):

    def test_bad_signature(self):
        ticket_view = self.api_post('new', api_signature='foo')
        assert ticket_view.status_int == 403

    def test_bad_token(self):
        ticket_view = self.api_post('new', api_key='foo')
        assert ticket_view.status_int == 403

    def test_bad_timestamp(self):
        ticket_view = self.api_post('new', api_timestamp=(datetime.utcnow()+timedelta(days=1)).isoformat())
        assert ticket_view.status_int == 403

    def test_new_ticket(self):
        summary = 'test new ticket'
        ticket_view = self.api_post(
            'new',
            summary=summary,
            status=self.tracker_globals.status_names.split()[0],
            labels='',
            description='',
            milestone='',
            assigned_to='')
        json = ticket_view.json['ticket']
        assert json['status'] == 'open', json
        assert json['summary'] == 'test new ticket', json
        assert json['reported_by'] == 'test-admin'

class TestRestUpdateTicket(TestRestApiBase):

    def setUp(self):
        super(TestRestUpdateTicket, self).setUp()
        summary = 'test new ticket'
        ticket_view = self.api_post(
            'new',
            summary=summary,
            status=self.tracker_globals.status_names.split()[0],
            labels='',
            description='',
            milestone='',
            assigned_to='')
        self.ticket_args = ticket_view.json['ticket']

    def test_ticket_index(self):
        tickets = self.api_post('')
        assert len(tickets.json['tickets']) == 1, tickets.json
        assert (tickets.json['tickets'][0]
                == dict(ticket_num=1, summary='test new ticket')), tickets.json['tickets'][0]

    def test_bad_signature(self):
        ticket_view = self.api_post('1/save', api_signature='foo')
        assert ticket_view.status_int == 403

    def test_bad_token(self):
        ticket_view = self.api_post('1/save', api_key='foo')
        assert ticket_view.status_int == 403

    def test_bad_timestamp(self):
        ticket_view = self.api_post('1/save', api_timestamp=(datetime.utcnow()+timedelta(days=1)).isoformat())
        assert ticket_view.status_int == 403

    def test_update_ticket(self):
        args = dict(self.ticket_args, summary='test update ticket', labels='',
                    assigned_to=self.ticket_args['assigned_to_id'] or '')
        for bad_key in ('assigned_to_id', 'created_date', 'reported_by', 'reported_by_id', 'super_id', 'sub_ids', '_id'):
            del args[bad_key]
        ticket_view = self.api_post('1/save', **h.encode_keys(args))
        assert ticket_view.status_int == 200, ticket_view.showbrowser()
        json = ticket_view.json['ticket']
        assert json['summary'] == 'test update ticket', json

class TestRestDiscussion(TestRestApiBase):

    def setUp(self):
        super(TestRestDiscussion, self).setUp()
        summary = 'test new ticket'
        ticket_view = self.api_post(
            'new',
            summary=summary,
            status=self.tracker_globals.status_names.split()[0],
            labels='',
            description='',
            milestone='',
            assigned_to='')
        self.ticket_args = ticket_view.json['ticket']

    def test_index(self):
        r = self.api_post('_discuss/')
        assert len(r.json['discussion']['threads']) == 1, r.json
        for t in r.json['discussion']['threads']:
            r = self.api_post('_discuss/thread/%s/' % t['_id'])
            assert len(r.json['thread']['posts']) == 0, r.json

    def test_post(self):
        discussion = self.api_post('_discuss/').json['discussion']
        post = self.api_post('_discuss/thread/%s/new' % discussion['threads'][0]['_id'],
                             text='This is a comment', wrap_args=None)
        thread = self.api_post('_discuss/thread/%s/' % discussion['threads'][0]['_id'])
        assert len(thread.json['thread']['posts']) == 1, thread.json
        assert post.json['post']['text'] == 'This is a comment', post.json
        reply = self.api_post(
            '_discuss/thread/%s/%s/reply' % (thread.json['thread']['_id'], post.json['post']['slug']),
            text='This is a reply', wrap_args=None)
        assert reply.json['post']['text'] == 'This is a reply', reply.json
        thread = self.api_post('_discuss/thread/%s/' % discussion['threads'][0]['_id'])
        assert len(thread.json['thread']['posts']) == 2, thread.json



