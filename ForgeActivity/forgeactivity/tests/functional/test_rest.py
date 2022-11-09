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

from tg import config
from alluratest.controller import TestRestApiBase


class TestActivityHasAccessAPI(TestRestApiBase):

    def setup_method(self, method, *args, **kwargs):
        super().setup_method(method, *args, **kwargs)
        self._enabled = config.get('activitystream.enabled', 'false')
        config['activitystream.enabled'] = 'true'

    def teardown_method(self, method, *args, **kwargs):
        super().teardown_method(method, *args, **kwargs)
        config['activitystream.enabled'] = self._enabled

    def test_has_access_no_params(self):
        self.api_get('/rest/p/test/activity/has_access', status=404)
        self.api_get('/rest/p/test/activity/has_access?user=root', status=404)
        self.api_get('/rest/p/test/activity/has_access?perm=read', status=404)

    def test_has_access_unknown_params(self):
        """Unknown user and/or permission always False for has_access API"""
        r = self.api_get(
            '/rest/p/test/activity/has_access?user=babadook&perm=read',
            user='root')
        assert r.status_int == 200
        assert r.json['result'] is False
        r = self.api_get(
            '/rest/p/test/activity/has_access?user=test-user&perm=jump',
            user='root')
        assert r.status_int == 200
        assert r.json['result'] is False

    def test_has_access_not_admin(self):
        """
        User which has no 'admin' permission on neighborhood can't use
        has_access API
        """
        self.api_get(
            '/rest/p/test/activity/has_access?user=test-admin&perm=admin',
            user='test-user',
            status=403)

    def test_has_access(self):
        r = self.api_get(
            '/rest/p/test/activity/has_access?user=test-admin&perm=admin',
            user='root')
        assert r.status_int == 200
        assert r.json['result'] is True
        r = self.api_get(
            '/rest/p/test/activity/has_access?user=test-user&perm=admin',
            user='root')
        assert r.status_int == 200
        assert r.json['result'] is False


    def test_user_api(self):
        r = self.api_get('/rest/u/test-user/activity')
        assert r.status_int == 200