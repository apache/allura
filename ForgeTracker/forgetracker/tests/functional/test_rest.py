from datetime import datetime, timedelta
from formencode import variabledecode

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
        user = M.User.query.get(username='test_admin')
        self.token = M.ApiToken(user_id=user._id)
        self.tracker_globals = TM.Globals.for_current_tracker()
        session(self.token).flush()
        self.mount_point = '/rest/p/test/bugs/'

    def api_post(self, path, api_key=None, api_timestamp=None, api_signature=None, **ticket_form):
        params = dict(ticket_form=ticket_form)
        params = variabledecode.variable_encode(params, add_repetitions=False)
        if api_key: params['api_key'] = api_key
        if api_timestamp: params['api_timestamp'] = api_timestamp
        if api_signature: params['api_signature'] = api_signature
        path = self.mount_point + path
        params = self.token.sign_request(path, params)
        response = self.app.post(
            path,
            params=params,
            status=[200,302,400,403])
        if response.status_int == 200:
            response.showbrowser()
            assert False, 'form error'
        elif response.status_int == 302:
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
        assert json['reported_by'] == 'test_admin'

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
                    assigned_to=self.ticket_args['assigned_to_id'] or '',
                    reported_by=self.ticket_args['reported_by_id'] or '',
                    super_id=self.ticket_args['super_id'] or '')
        ticket_view = self.api_post('1/save', **args)
        assert ticket_view.status_int == 200, ticket_view.showbrowser()
        json = ticket_view.json['ticket']
        assert json['summary'] == 'test update ticket', json

