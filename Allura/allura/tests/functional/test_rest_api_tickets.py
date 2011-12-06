from pprint import pprint
from datetime import datetime, timedelta
import json

from pylons import c
from ming.orm import session

from allura import model as M
from allura.lib import helpers as h
from alluratest.controller import TestController, TestRestApiBase


class TestApiTicket(TestRestApiBase):

    def set_api_ticket(self, expire=None):
        if not expire:
            expire = timedelta(days=1)
        api_ticket = M.ApiTicket(user_id=self.user._id, capabilities={'import': ['Projects','test']},
                                 expires=datetime.utcnow() + expire)
        session(api_ticket).flush()
        self.set_api_token(api_ticket)

    def test_bad_signature(self):
        self.set_api_ticket()
        r = self.api_post('/rest/p/test/wiki/', api_signature='foo')
        assert r.status_int == 403

    def test_bad_token(self):
        self.set_api_ticket()
        r = self.api_post('/rest/p/test/wiki/', api_key='foo')
        assert r.status_int == 403

    def test_bad_timestamp(self):
        self.set_api_ticket()
        r = self.api_post('/rest/p/test/wiki/', api_timestamp=(datetime.utcnow() + timedelta(days=1)).isoformat())
        assert r.status_int == 403

    def test_bad_path(self):
        self.set_api_ticket()
        r = self.api_post('/rest/1/test/wiki/')
        assert r.status_int == 404
        r = self.api_post('/rest/p/1223/wiki/')
        assert r.status_int == 404
        r = self.api_post('/rest/p/test/12wiki/')
        assert r.status_int == 404

    def test_no_api(self):
        self.set_api_ticket()
        r = self.api_post('/rest/p/test/admin/')
        assert r.status_int == 404

    def test_project_ping(self):
        self.set_api_ticket()
        r = self.api_get('/rest/p/test/wiki/Home/')
        assert r.status_int == 200
        assert r.json['title'] == 'Home', r.json

    def test_project_ping_expired_ticket(self):
        self.set_api_ticket(timedelta(seconds=-1))
        r = self.api_post('/rest/p/test/wiki/')
        assert r.status_int == 403

    def test_subproject_ping(self):
        self.set_api_ticket()
        r = self.api_get('/rest/p/test/sub1/wiki/Home/')
        assert r.status_int == 200
        assert r.json['title'] == 'Home', r.json
