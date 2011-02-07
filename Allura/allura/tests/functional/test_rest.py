from pprint import pprint
from datetime import datetime, timedelta
import json

from pylons import c
from ming.orm import session

from allura import model as M
from allura.lib import helpers as h
from alluratest.controller import TestController, TestRestApiBase


class TestRestHome(TestRestApiBase):

    def test_bad_signature(self):
        r = self.api_post('/rest/p/test/home/', api_signature='foo')
        assert r.status_int == 403

    def test_bad_token(self):
        r = self.api_post('/rest/p/test/home/', api_key='foo')
        assert r.status_int == 403

    def test_bad_timestamp(self):
        r = self.api_post('/rest/p/test/home/', api_timestamp=(datetime.utcnow() + timedelta(days=1)).isoformat())
        assert r.status_int == 403

    def test_bad_path(self):
        r = self.api_post('/rest/1/test/home/')
        assert r.status_int == 404
        r = self.api_post('/rest/p/1223/home/')
        assert r.status_int == 404
        r = self.api_post('/rest/p/test/12home/')
        assert r.status_int == 404

    def test_no_api(self):
        r = self.api_post('/rest/p/test/admin/')
        assert r.status_int == 404

    def test_project_ping(self):
        r = self.api_post('/rest/p/test/home/')
        assert r.status_int == 200
        assert r.json['shortname'] == 'test'

    def test_subproject_ping(self):
        r = self.api_post('/rest/p/test/sub1/home/')
        assert r.status_int == 200
        assert r.json['shortname'] == 'test/sub1'
