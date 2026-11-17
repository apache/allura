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

import json

import mock
import pytest
from tg import config

from allura.controllers.rest import Oauth2Validator
from allura.tests import TestController

AS_PATH = '/.well-known/oauth-authorization-server'
PR_PATH = '/.well-known/oauth-protected-resource'
ANON = {'username': '*anonymous'}


class TestOAuthDiscoveryDocuments(TestController):

    @pytest.fixture(autouse=True)
    def oauth2_config(self):
        with mock.patch.dict(config, {'auth.oauth2.enabled': True}):
            yield

    @pytest.fixture
    def full_config(self):
        with mock.patch.dict(config, {'auth.oauth2.scopes_supported': 'read write',
                                      'auth.oauth2.protected_resources': '/rest/p/test/wiki /rest/p/other',
                                      'auth.oauth2.dcr.enabled': 'true',
                                      'auth.oauth2.cimd.enabled': 'true'}):
            yield

    @property
    def root(self):
        return config['base_url'].rstrip('/')

    def test_authorization_server_metadata_defaults(self):
        r = self.app.get(AS_PATH, extra_environ=ANON)
        assert r.json == {
            'issuer': self.root,
            'authorization_endpoint': self.root + '/auth/oauth2/authorize',
            'token_endpoint': self.root + '/rest/oauth2/token',
            'response_types_supported': ['code'],
            'grant_types_supported': ['authorization_code', 'refresh_token'],
            'code_challenge_methods_supported': ['S256'],
            'token_endpoint_auth_methods_supported': ['client_secret_post', 'client_secret_basic'],
        }

    def test_authorization_server_metadata_configured(self, full_config):
        r = self.app.get(AS_PATH, extra_environ=ANON)
        assert r.body == json.dumps({
            'issuer': self.root,
            'authorization_endpoint': self.root + '/auth/oauth2/authorize',
            'token_endpoint': self.root + '/rest/oauth2/token',
            'response_types_supported': ['code'],
            'grant_types_supported': ['authorization_code', 'refresh_token'],
            'code_challenge_methods_supported': ['S256'],
            'scopes_supported': ['read', 'write'],
            'token_endpoint_auth_methods_supported': ['client_secret_post', 'client_secret_basic', 'none'],
            'registration_endpoint': self.root + '/rest/oauth2/register',
            'client_id_metadata_document_supported': True,
        }, indent=2).encode()

    def test_validator_decides_dcr_and_cimd(self, full_config):
        with mock.patch.object(Oauth2Validator, 'dcr_enabled', return_value=False), \
                mock.patch.object(Oauth2Validator, 'cimd_enabled', return_value=False):
            doc = self.app.get(AS_PATH, extra_environ=ANON).json
        assert 'registration_endpoint' not in doc
        assert 'client_id_metadata_document_supported' not in doc
        assert 'none' not in doc['token_endpoint_auth_methods_supported']

    def test_protected_resource_metadata(self, full_config):
        expected = {
            'resource': self.root + '/rest/p/test/wiki',
            'authorization_servers': [self.root],
            'scopes_supported': ['read', 'write'],
            'bearer_methods_supported': ['header'],
        }
        for path in [PR_PATH, PR_PATH + '/', PR_PATH + '/rest/p/test/wiki', PR_PATH + '/rest/p/test/wiki/',
                     PR_PATH + '/rest/p/test/wiki/Home']:
            assert self.app.get(path, extra_environ=ANON).json == expected, path
        assert self.app.get(PR_PATH + '/rest/p/other', extra_environ=ANON).json['resource'] == \
            self.root + '/rest/p/other'

    def test_protected_resource_metadata_unknown_resource(self, full_config):
        for path in [PR_PATH + '/rest/p/test', PR_PATH + '/rest/p/test/wikifoo', PR_PATH + '/rest/p/test/wiki/../x']:
            self.app.get(path, extra_environ=ANON, status=404)

    def test_protected_resource_metadata_needs_a_resource(self):
        self.app.get(PR_PATH, extra_environ=ANON, status=404)

    def test_not_served_when_oauth2_disabled(self, full_config):
        with mock.patch.dict(config, {'auth.oauth2.enabled': False}):
            self.app.get(AS_PATH, extra_environ=ANON, status=404)
            self.app.get(PR_PATH, extra_environ=ANON, status=404)

    def test_unknown_documents(self, full_config):
        for path in ['/.well-known/', '/.well-known/nope', AS_PATH + '/extra']:
            self.app.get(path, extra_environ=ANON, status=404)

    def test_response_headers(self, full_config):
        for user in [ANON, {'username': 'test-admin'}]:
            for path in [AS_PATH, PR_PATH]:
                r = self.app.get(path, extra_environ=user)
                assert r.status_int == 200
                assert r.content_type == 'application/json'
                assert r.headers['Cache-Control'] == 'public, max-age=3600'
                assert r.headers['Access-Control-Allow-Origin'] == '*'
                assert 'Pragma' not in r.headers

    def test_get_only(self, full_config):
        for path in [AS_PATH, PR_PATH]:
            r = self.app.post(path, extra_environ=ANON, status=405)
            assert r.headers['Allow'] == 'GET'
