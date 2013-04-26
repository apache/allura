# -*- coding: utf-8 -*-

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

from datetime import datetime, timedelta

from pylons import app_globals as g
from nose.tools import assert_equal
import mock
import json

from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase
from allura.lib import helpers as h
from allura import model as M

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
                'viewable_by-0.id':'all'})
        r = self.api_get('/rest/p/test/wiki/tést/')
        assert r.status_int == 200
        assert r.json['title'].encode('utf-8') == 'tést', r.json

    @td.with_wiki
    def test_deny_access(self):
        wiki = M.Project.query.get(shortname='test').app_instance('wiki')
        anon_read_perm = M.ACE.allow(M.ProjectRole.by_name('*anonymous')._id, 'read')
        auth_read_perm = M.ACE.allow(M.ProjectRole.by_name('*authenticated')._id, 'read')
        acl = wiki.config.acl
        if anon_read_perm in acl:
            acl.remove(anon_read_perm)
        if auth_read_perm in acl:
            acl.remove(auth_read_perm)
        self.app.get('/rest/p/test/wiki/Home/',
                     extra_environ={'username': '*anonymous'},
                     status=401)
        self.app.get('/rest/p/test/wiki/Home/',
                     extra_environ={'username': 'test-user-0'},
                     status=401)

    def test_index(self):
        eps = {
                'site_stats': {
                    'foo_24hr': lambda: 42,
                    'bar_24hr': lambda: 84,
                    'qux_24hr': lambda: 0,
                },
            }
        with mock.patch.dict(g.entry_points, eps):
            response = self.app.get('/rest/')
            assert_equal(response.json, {
                'site_stats': {
                        'foo_24hr': 42,
                        'bar_24hr': 84,
                        'qux_24hr': 0,
                    },
                })
