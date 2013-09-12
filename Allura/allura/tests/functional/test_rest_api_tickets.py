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

from ming.orm import session

from allura import model as M
from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase


class TestApiTicket(TestRestApiBase):

    def set_api_ticket(self, expire=None):
        if not expire:
            expire = timedelta(days=1)
        test_admin = M.User.query.get(username='test-admin')
        api_ticket = M.ApiTicket(user_id=test_admin._id, capabilities={'import': ['Projects','test']},
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

    @td.with_wiki
    def test_project_ping(self):
        self.set_api_ticket()
        r = self.api_get('/rest/p/test/wiki/Home/')
        assert r.status_int == 200
        assert r.json['title'] == 'Home', r.json

    def test_project_ping_expired_ticket(self):
        self.set_api_ticket(timedelta(seconds=-1))
        r = self.api_post('/rest/p/test/wiki/')
        assert r.status_int == 403

    @td.with_tool('test/sub1', 'Wiki', 'wiki')
    def test_subproject_ping(self):
        self.set_api_ticket()
        r = self.api_get('/rest/p/test/sub1/wiki/Home/')
        assert r.status_int == 200
        assert r.json['title'] == 'Home', r.json
