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
import requests
import tg
from mock import patch, call, Mock
from unittest import TestCase

from allura.tests import TestController
from allura import model as M


class TestGitHubImportController(TestController, TestCase):

    def test_index(self):
        r = self.app.get('/p/import_project/github/')
        assert 'GitHub Project Importer' in r
        assert '<input id="user_name" name="user_name" value="" autofocus/>' in r
        assert '<input id="project_name" name="project_name" value="" />' in r
        assert '<input id="project_shortname" name="project_shortname" value=""/>' in r
        assert '<input name="tool_option" value="import_history" type="checkbox" checked="checked"/>' in r

    def test_login_overlay(self):
        r = self.app.get('/p/import_project/github/',
                         extra_environ=dict(username='*anonymous'))
        self.assertIn('GitHub Project Importer', r)
        self.assertIn('Login Required', r)

        r = self.app.post('/p/import_project/github/process',
                          extra_environ=dict(username='*anonymous'), status=302)
        self.assertIn('/auth/', r.location)


class TestGitHubOAuth(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        tg.config['github_importer.client_id'] = 'client_id'
        tg.config['github_importer.client_secret'] = 'secret'

    @patch('forgeimporters.github.OAuth2Session')
    @patch('forgeimporters.github.session')
    def test_oauth_flow(self, session, oauth):
        redirect = 'http://localhost/p/import_project/github/oauth_callback'
        oauth_instance = Mock()
        oauth_instance.authorization_url.return_value = (redirect, 'state')
        oauth_instance.fetch_token.return_value = {'access_token': 'abc'}
        oauth.return_value = oauth_instance

        user = M.User.by_username('test-admin')
        assert user.get_tool_data('GitHubProjectImport', 'token') is None
        r = self.app.get('/p/import_project/github/')
        assert r.status_int == 302
        assert r.location == redirect
        session.__setitem__.assert_has_calls([
            call('github.oauth.state', 'state'),
            call('github.oauth.redirect',
                 'http://localhost/p/import_project/github/')
        ])
        assert session.save.call_count == 1

        r = self.app.get(redirect)
        session.get.assert_has_calls([
            call('github.oauth.state'),
            call('github.oauth.redirect', '/')
        ])
        user = M.User.by_username('test-admin')
        assert user.get_tool_data('GitHubProjectImport', 'token') == 'abc'

        with patch('forgeimporters.github.requests.post') as valid_access_token_post:
            valid_access_token_post.return_value = Mock(status_code=200)
            r = self.app.get('/p/import_project/github/')

        # token in user data, so oauth isn't triggered
        assert r.status_int == 200

        valid_access_token_post.assert_called_once_with('https://api.github.com/applications/client_id/token',
                                                        auth=requests.auth.HTTPBasicAuth('client_id', 'secret'),
                                                        json={'access_token': 'abc'},
                                                        timeout=10)


    def test_project_import_login_required(self):
        r = self.app.get('/p/import_project/github/', extra_environ=dict(username='*anonymous'))
        assert None == r.location
        r.mustcontain('Login Required')
