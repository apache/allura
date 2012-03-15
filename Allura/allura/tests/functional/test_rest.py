# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase
from allura.lib import helpers as h

class TestRestHome(TestRestApiBase):

    def test_bad_signature(self):
        r = self.api_post('/rest/p/test/wiki/', api_signature='foo')
        assert r.status_int == 403

    def test_bad_token(self):
        r = self.api_post('/rest/p/test/wiki/', api_key='foo')
        assert r.status_int == 403

    def test_bad_timestamp(self):
        r = self.api_post('/rest/p/test/wiki/', api_timestamp=(datetime.utcnow() + timedelta(days=1)).isoformat())
        assert r.status_int == 403

    def test_bad_path(self):
        r = self.api_post('/rest/1/test/wiki/')
        assert r.status_int == 404
        r = self.api_post('/rest/p/1223/wiki/')
        assert r.status_int == 404
        r = self.api_post('/rest/p/test/12wiki/')
        assert r.status_int == 404

    def test_no_api(self):
        r = self.api_post('/rest/p/test/admin/')
        assert r.status_int == 404

    @td.with_wiki
    def test_project_ping(self):
        r = self.api_get('/rest/p/test/wiki/Home/')
        assert r.status_int == 200
        assert r.json['title'] == 'Home', r.json

    @td.with_tool('test/sub1', 'Wiki', 'wiki')
    def test_subproject_ping(self):
        r = self.api_get('/rest/p/test/sub1/wiki/Home/')
        assert r.status_int == 200
        assert r.json['title'] == 'Home', r.json

    def test_project_code(self):
        r = self.api_get('/rest/p/test/')
        assert r.status_int == 200

    def test_unicode(self):
        self.app.post(
            '/wiki/tést/update',
            params={
                'title':'tést',
                'text':'sometext',
                'labels':'',
                'labels_old':'',
                'viewable_by-0.id':'all'})
        r = self.api_get('/rest/p/test/wiki/tést/')
        assert r.status_int == 200
        assert r.json['title'].encode('utf-8') == 'tést', r.json

