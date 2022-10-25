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

import os
import json

from tg import config

from allura.lib import helpers as h
from alluratest.controller import TestRestApiBase


class TestImportController(TestRestApiBase):  # TestController):

    def setup_method(self, method):
        super().setup_method(method)
        here_dir = os.path.dirname(__file__)
        self.app.get('/discussion/')
        self.json_text = open(here_dir + '/data/sf.json').read()

    def test_no_capability(self):
        with h.push_config(config, **{'oauth.can_import_forum': 'some,fake,tokens'}):
            resp = self.api_post('/rest/p/test/discussion/perform_import',
                                 doc=self.json_text,
                                 status=403)

        with h.push_config(config, **{'oauth.can_import_forum': self.token('test-admin').api_key}):
            resp = self.api_post('/rest/p/test/discussion/perform_import',
                                 doc=self.json_text)
            assert resp.status_int == 200

    def test_validate_import(self):
        r = self.api_post('/rest/p/test/discussion/validate_import',
                          doc=self.json_text)
        assert not r.json['errors']

    def test_import_anon(self):
        with h.push_config(config, **{'oauth.can_import_forum': self.token('test-admin').api_key}):
            r = self.api_post('/rest/p/test/discussion/perform_import',
                              doc=self.json_text)
            assert not r.json['errors'], r.json['errors']
            r = self.app.get('/p/test/discussion/')
            assert 'Open Discussion' in str(r)
            assert 'Welcome to Open Discussion' in str(r)
            for link in r.html.findAll('a'):
                if 'Welcome to Open Discussion' in str(link):
                    break
            r = self.app.get(link.get('href'))
            assert '2009-11-19' in str(r)
            assert 'Welcome to Open Discussion' in str(r)
            assert 'Anonymous' in str(r)

    def test_import_map(self):
        with h.push_config(config, **{'oauth.can_import_forum': self.token('test-admin').api_key}):
            r = self.api_post('/rest/p/test/discussion/perform_import',
                              doc=self.json_text,
                              username_mapping=json.dumps(dict(rick446='test-user')))
            assert not r.json['errors'], r.json['errors']
            r = self.app.get('/p/test/discussion/')
            assert 'Open Discussion' in str(r)
            assert 'Welcome to Open Discussion' in str(r)
            for link in r.html.findAll('a'):
                if 'Welcome to Open Discussion' in str(link):
                    break
            r = self.app.get(link.get('href'))
            assert '2009-11-19' in str(r)
            assert 'Welcome to Open Discussion' in str(r)
            assert 'Test User' in str(r)
            assert 'Anonymous' not in str(r)

    def test_import_create(self):
        with h.push_config(config, **{'oauth.can_import_forum': self.token('test-admin').api_key}):
            r = self.api_post('/rest/p/test/discussion/perform_import',
                              doc=self.json_text, create_users='True')
            assert not r.json['errors'], r.json['errors']
            r = self.app.get('/p/test/discussion/')
            assert 'Open Discussion' in str(r)
            assert 'Welcome to Open Discussion' in str(r)
            for link in r.html.findAll('a'):
                if 'Welcome to Open Discussion' in str(link):
                    break
            r = self.app.get(link.get('href'))
            assert '2009-11-19' in str(r)
            assert 'Welcome to Open Discussion' in str(r)
            assert 'Anonymous' not in str(r)
            assert 'test-rick446' in str(r)

    @staticmethod
    def time_normalize(t):
        return t.replace('T', ' ').replace('Z', '')

    def verify_ticket(self, from_api, org):
        assert from_api['status'] == org['status']
        assert from_api['description'] == org['description']
        assert from_api['summary'] == org['summary']
        assert from_api['ticket_num'] == org['id']
        assert (from_api['created_date'] ==
                     self.time_normalize(org['date']))
        assert (from_api['mod_date'] ==
                     self.time_normalize(org['date_updated']))
        assert (from_api['custom_fields']
                     ['_resolution'] == org['resolution'])
        assert from_api['custom_fields']['_cc'] == org['cc']
        assert from_api['custom_fields']['_private'] == org['private']
