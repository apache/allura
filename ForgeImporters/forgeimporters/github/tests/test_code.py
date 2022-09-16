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
from mock import Mock, patch
from ming.odm import ThreadLocalORMSession

from allura.tests import TestController
from allura.tests.decorators import with_tool
from allura import model as M
from alluratest.controller import setup_unit_test
from forgeimporters.github.code import GitHubRepoImporter
from forgeimporters.github import GitHubOAuthMixin


# important to be distinct from 'test' which ForgeGit uses, so that the
# tests can run in parallel and not clobber each other
test_project_with_repo = 'test2'
with_git = with_tool(test_project_with_repo, 'git', 'src', 'git')


class TestGitHubRepoImporter(TestCase):

    def setup_method(self, method):
        setup_unit_test()

    def _make_project(self, gh_proj_name=None):
        project = Mock()
        project.get_tool_data.side_effect = lambda *args: gh_proj_name
        return project

    @patch('forgeimporters.github.code.M')
    @patch('forgeimporters.github.code.g')
    @patch('forgeimporters.github.code.GitHubProjectExtractor')
    def test_import_tool_happy_path(self, ghpe, g, M):
        ghpe.return_value.get_repo_url.return_value = 'http://remote/clone/url/'
        p = self._make_project(gh_proj_name='myproject')
        u = Mock(name='c.user')
        app = p.install_app.return_value
        app.config.options.mount_point = 'code'
        app.url = 'foo'
        GitHubRepoImporter().import_tool(
            p, u, project_name='project_name', user_name='testuser')
        p.install_app.assert_called_once_with(
            'Git',
            mount_point='code',
            mount_label='Code',
            init_from_url='http://remote/clone/url/',
            import_id={'source': 'GitHub', 'project_name': 'testuser/project_name'})
        M.AuditLog.log.assert_called_once_with(
            'import tool code from testuser/project_name on GitHub',
            project=p, user=u, url='foo')
        g.post_event.assert_called_once_with('project_updated')


class TestGitHubImportController(TestController, TestCase):

    @with_git
    def test_index(self):
        r = self.app.get(
            f'/p/{test_project_with_repo}/admin/ext/import/github-repo/')
        self.assertIsNotNone(r.html.find(attrs=dict(name="gh_user_name")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="gh_project_name")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_label")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_point")))

    @with_git
    @patch('forgeimporters.github.requests')
    @patch('forgeimporters.base.import_tool')
    def test_create(self, import_tool, requests):
        requests.head.return_value.status_code = 200
        params = dict(
            gh_user_name='spooky',
            gh_project_name='poop',
            mount_label='mylabel',
            mount_point='mymount',
        )
        r = self.app.post(
            '/p/{}/admin/ext/import/github-repo/create'.format(
                test_project_with_repo),
            params,
            status=302)
        self.assertEqual(
            r.location, 'http://localhost/p/{}/admin/'.format(
                test_project_with_repo))
        self.assertEqual(
            'mymount', import_tool.post.call_args[1]['mount_point'])
        self.assertEqual(
            'mylabel', import_tool.post.call_args[1]['mount_label'])
        self.assertEqual(
            'poop', import_tool.post.call_args[1]['project_name'])
        self.assertEqual('spooky', import_tool.post.call_args[1]['user_name'])
        self.assertEqual(requests.head.call_count, 1)

    @with_git
    @patch('forgeimporters.github.requests')
    @patch('forgeimporters.base.import_tool')
    def test_create_limit(self, import_tool, requests):
        requests.head.return_value.status_code = 200
        project = M.Project.query.get(shortname=test_project_with_repo)
        project.set_tool_data('GitHubRepoImporter', pending=1)
        ThreadLocalORMSession.flush_all()
        params = dict(
            gh_user_name='spooky',
            gh_project_name='poop',
            mount_label='mylabel',
            mount_point='mymount',
        )
        r = self.app.post(
            '/p/{}/admin/ext/import/github-repo/create'.format(
                test_project_with_repo),
            params,
            status=302).follow()
        self.assertIn('Please wait and try again', r)
        self.assertEqual(import_tool.post.call_count, 0)

    @with_git
    @patch.object(GitHubOAuthMixin, 'oauth_begin')
    def test_oauth(self, oauth_begin):
        self.app.get(
            f'/p/{test_project_with_repo}/admin/ext/import/github-repo/')
        self.assertEqual(oauth_begin.call_count, 1)
