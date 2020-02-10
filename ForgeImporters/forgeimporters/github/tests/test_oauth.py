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

from __future__ import unicode_literals
from __future__ import absolute_import
from unittest import TestCase

from mock import Mock, patch, MagicMock
from tg import tmpl_context as c, config
from webob.exc import HTTPFound

from allura.tests import TestController
from allura.tests.decorators import raises
from forgeimporters.github import GitHubOAuthMixin


class TestGitHubOAuthMixin(TestController, TestCase):

    def setUp(self):
        super(TestGitHubOAuthMixin, self).setUp()
        c.user = Mock()
        self.mix = GitHubOAuthMixin()

    def test_oauth_has_access_no_scope(self):
        self.assertFalse(self.mix.oauth_has_access(None))
        self.assertFalse(self.mix.oauth_has_access(''))

    def test_oauth_has_access_no_token(self):
        c.user.get_tool_data.return_value = None
        self.assertFalse(self.mix.oauth_has_access('write:repo_hook'))

    @patch('forgeimporters.github.requests')
    def test_oauth_has_access_no_headers(self, req):
        c.user.get_tool_data.return_value = 'token'
        self.assertFalse(self.mix.oauth_has_access('write:repo_hook'))
        req.head.assert_called_once_with('https://api.github.com/?access_token=token', timeout=10)

    @patch('forgeimporters.github.requests')
    def test_oauth_has_access_with_headers(self, req):
        c.user.get_tool_data.return_value = 'token'
        req.head.return_value.headers = {'X-OAuth-Scopes': ''}
        self.assertFalse(self.mix.oauth_has_access('write:repo_hook'))
        req.head.return_value.headers = {'X-OAuth-Scopes': 'some, other:scopes'}
        self.assertFalse(self.mix.oauth_has_access('write:repo_hook'))
        req.head.return_value.headers = {'X-OAuth-Scopes': 'write:repo_hook, user'}
        self.assertTrue(self.mix.oauth_has_access('write:repo_hook'))

    @patch.dict(config, {'github_importer.client_id': '123456',
                         'github_importer.client_secret': 'deadbeef'})
    @patch('forgeimporters.github.OAuth2Session', MagicMock())
    @patch('forgeimporters.github.session', MagicMock())
    @patch('forgeimporters.github.request', MagicMock())
    def test_oauth_callback_complete(self):
        with patch.object(self.mix, 'oauth_callback_complete') as _mock, \
                patch('forgeimporters.github.redirect') as tg_redir:
            self.mix.oauth_callback()
        self.assertEqual(_mock.call_count, 1)
        self.assertEqual(tg_redir.call_count, 1)
