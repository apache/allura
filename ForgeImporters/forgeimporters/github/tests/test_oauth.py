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

from unittest import TestCase
from alluratest.controller import setup_unit_test

from mock import Mock, patch, MagicMock
from tg import tmpl_context as c, config

from allura.tests import TestController
from forgeimporters.github import GitHubOAuthMixin


class TestGitHubOAuthMixin(TestController, TestCase):

    def setup_method(self, method):
        super().setup_method(method)
        setup_unit_test()
        c.user = Mock()
        self.mix = GitHubOAuthMixin()

    def test_oauth_has_access_no_scope(self):
        self.assertFalse(self.mix.oauth_has_access(None))
        self.assertFalse(self.mix.oauth_has_access(''))

    def test_oauth_has_access_no_token(self):
        c.user.get_tool_data.return_value = None
        self.assertFalse(self.mix.oauth_has_access('write:repo_hook'))

    @patch.dict(config, {'github_importer.client_id': '123456',
                         'github_importer.client_secret': 'deadbeef'})
    @patch('forgeimporters.github.requests')
    def test_oauth_has_access_no(self, req):
        c.user.get_tool_data.return_value = 'some-token'
        req.post.return_value = Mock(status_code=404, json=Mock(return_value={}))
        self.assertFalse(self.mix.oauth_has_access('write:repo_hook'))
        call_args = req.post.call_args[0]
        self.assertEqual(call_args, ('https://api.github.com/applications/123456/token',))
        call_kwargs = req.post.call_args[1]
        assert call_kwargs['auth']
        self.assertEqual(call_kwargs['json'], {'access_token': 'some-token'})

    @patch.dict(config, {'github_importer.client_id': '123456',
                         'github_importer.client_secret': 'deadbeef'})
    @patch('forgeimporters.github.requests')
    def test_oauth_has_access_yes(self, req):
        c.user.get_tool_data.return_value = 'some-token'

        req.post.return_value.json.return_value = {'scopes': []}
        self.assertFalse(self.mix.oauth_has_access('write:repo_hook'))

        req.post.return_value.json.return_value = {'scopes': ['some', 'other:scopes']}
        self.assertFalse(self.mix.oauth_has_access('write:repo_hook'))

        req.post.return_value.json.return_value = {'scopes': ['write:repo_hook', 'user']}
        self.assertTrue(self.mix.oauth_has_access('write:repo_hook'))

    @patch.dict(config, {'github_importer.client_id': '123456',
                         'github_importer.client_secret': 'deadbeef'})
    @patch('forgeimporters.github.OAuth2Session', MagicMock())
    @patch('forgeimporters.github.session', MagicMock())
    @patch('forgeimporters.github.request', MagicMock())
    def test_oauth_callback_complete(self):
        with patch.object(self.mix, 'oauth_callback_complete') as _mock, \
                patch('forgeimporters.github.redirect') as tg_redir:
            self.mix.handle_oauth_callback()
        self.assertEqual(_mock.call_count, 1)
        self.assertEqual(tg_redir.call_count, 1)
