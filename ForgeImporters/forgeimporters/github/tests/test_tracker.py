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

from mock import patch
from ming.odm import ThreadLocalODMSession

from allura.tests import TestController
from allura.tests.decorators import with_tool
from allura import model as M

from forgeimporters.github import GitHubOAuthMixin

# important to be distinct from 'test' which ForgeTracker uses, so that
# the tests can run in parallel and not clobber each other
test_project_with_tracker = 'test2'
with_tracker = with_tool(test_project_with_tracker,
                         'tickets', 'spooky-issues', 'tickets')


class TestGitHubTrackerImportController(TestController):

    url = '/p/%s/admin/ext/import/github-tracker/' % test_project_with_tracker

    @with_tracker
    def test_index(self):
        r = self.app.get(self.url)
        assert r.html.find(attrs=dict(name='gh_user_name')) is not None
        assert r.html.find(attrs=dict(name='gh_project_name')) is not None
        assert r.html.find(attrs=dict(name='mount_label')) is not None
        assert r.html.find(attrs=dict(name='mount_point')) is not None

    @with_tracker
    @patch('forgeimporters.github.requests')
    @patch('forgeimporters.base.import_tool')
    def test_create(self, import_tool, requests):
        requests.head.return_value.status_code = 200
        params = dict(
            gh_user_name='spooky',
            gh_project_name='mulder',
            mount_point='issues',
            mount_label='Issues')
        r = self.app.post(self.url + 'create', params, status=302)
        assert r.location == 'http://localhost/p/%s/admin/' % test_project_with_tracker
        assert 'Issues' == import_tool.post.call_args[1]['mount_label']
        assert 'issues' == import_tool.post.call_args[1]['mount_point']
        assert 'mulder' == import_tool.post.call_args[1]['project_name']
        assert 'spooky' == import_tool.post.call_args[1]['user_name']
        assert requests.head.call_count == 1

    @with_tracker
    @patch('forgeimporters.github.requests')
    @patch('forgeimporters.base.import_tool')
    def test_create_limit(self, import_tool, requests):
        requests.head.return_value.status_code = 200
        p = M.Project.query.get(shortname=test_project_with_tracker)
        p.set_tool_data('GitHubTrackerImporter', pending=1)
        ThreadLocalODMSession.flush_all()
        params = dict(
            gh_user_name='spooky',
            gh_project_name='mulder',
            mount_point='issues',
            mount_label='Issues')
        r = self.app.post(self.url + 'create', params, status=302).follow()
        assert 'Please wait and try again' in r
        assert import_tool.post.call_count == 0

    @with_tracker
    @patch.object(GitHubOAuthMixin, 'oauth_begin')
    def test_oauth(self, oauth_begin):
        self.app.get(self.url)
        assert oauth_begin.call_count == 1
