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
from nose.tools import assert_equal
from mock import Mock, patch, call

from allura.tests import TestController
from allura.tests.decorators import with_tool
from alluratest.controller import setup_basic_test
from forgeimporters.github.wiki import GitHubWikiImporter


# important to be distinct from 'test' which ForgeWiki uses, so that the tests can run in parallel and not clobber each other
test_project_with_wiki = 'test2'
with_wiki = with_tool(test_project_with_wiki, 'wiki', 'w', 'wiki')


class TestGitHubRepoImporter(TestCase):

    def _make_project(self, gh_proj_name=None):
        project = Mock()
        project.get_tool_data.side_effect = lambda *args: gh_proj_name
        return project

    @patch('forgeimporters.github.wiki.g')
    @patch('forgeimporters.github.wiki.GitHubProjectExtractor')
    def test_import_tool_happy_path(self, ghpe, g):
        with patch('forgeimporters.github.wiki.GitHubWikiImporter.get_wiki_pages'), patch('forgeimporters.github.wiki.c'):
            ghpe.return_value.has_wiki.return_value = True
            p = self._make_project(gh_proj_name='myproject')
            GitHubWikiImporter().import_tool(p, Mock(name='c.user'), project_name='project_name', user_name='testuser')
            p.install_app.assert_called_once_with(
                'Wiki',
                mount_point='wiki',
                mount_label='Wiki')
            g.post_event.assert_called_once_with('project_updated')


class TestGitHubWikiImporter(TestCase):

    def setUp(self):
        setup_basic_test()
        self.blob1 = Mock()
        self.blob1.name = 'Home.md'
        self.blob1.data_stream.read.return_value = '# test message'

        self.blob2 = Mock()
        self.blob2.name = 'Home2.creole'
        self.blob2.data_stream.read.return_value = '**test message**'

        self.blob3 = Mock()
        self.blob3.name = 'Home3.rest'
        self.blob3.data_stream.read.return_value = 'test message'

        self.commit1 = Mock()
        self.commit1.tree.blobs = [self.blob1]
        self.commit1.committed_date = 1256301446

        self.commit2 = Mock()
        self.commit2.tree.blobs = [self.blob1, self.blob2, self.blob3]
        self.commit2.committed_date = 1256291446

    @patch('forgeimporters.github.wiki.WM.Page.upsert')
    @patch('forgeimporters.github.wiki.h.render_any_markup')
    def test_get_blobs_without_history(self, render, upsert):
        upsert.text = Mock()
        GitHubWikiImporter().get_blobs_without_history(self.commit2)
        assert_equal(upsert.call_args_list, [call('Home'), call('Home2'), call('Home3')])

        assert_equal(render.call_args_list, [
            call('Home.md', u'# test message'),
            call('Home2.creole', u'**test message**'),
            call('Home3.rest', u'test message')])

    @patch('forgeimporters.github.wiki.git.Repo')
    @patch('forgeimporters.github.wiki.mkdtemp')
    def test_clone_from(self, path, repo):
        with patch('forgeimporters.github.wiki.rmtree'):
            path.return_value = 'temp_path'
            GitHubWikiImporter().get_wiki_pages('wiki_url')
            repo.clone_from.assert_called_with('wiki_url', to_path='temp_path', bare=True)

    @patch('forgeimporters.github.wiki.git.Repo._clone')
    @patch('forgeimporters.github.wiki.GitHubWikiImporter.get_blobs_with_history')
    @patch('forgeimporters.github.wiki.GitHubWikiImporter.get_blobs_without_history')
    def test_get_commits_with_history(self, without_history, with_history, clone):
        repo = clone.return_value
        repo.iter_commits.return_value = [self.commit1, self.commit2]
        GitHubWikiImporter().get_wiki_pages('wiki_url', history=True)
        assert_equal(with_history.call_count, 2)
        assert_equal(without_history.call_count, 0)

    @patch('forgeimporters.github.wiki.GitHubWikiImporter.get_blobs_with_history')
    @patch('forgeimporters.github.wiki.GitHubWikiImporter.get_blobs_without_history')
    def test_get_commits_without_history(self, without_history, with_history):
        with patch('forgeimporters.github.wiki.git.Repo._clone'):
            GitHubWikiImporter().get_wiki_pages('wiki_url')
            assert_equal(with_history.call_count, 0)
            assert_equal(without_history.call_count, 1)

    @patch('forgeimporters.github.wiki.WM.Page.upsert')
    @patch('forgeimporters.github.wiki.h.render_any_markup')
    def test_get_blobs_with_history(self, render, upsert):
        self.commit2.stats.files = {"Home.md": self.blob1}
        self.commit2.tree = {"Home.md": self.blob1}
        GitHubWikiImporter().get_blobs_with_history(self.commit2)
        assert_equal(upsert.call_args_list, [call('Home')])
        assert_equal(render.call_args_list, [call('Home.md', u'# test message')])


class TestGitHubWikiImportController(TestController, TestCase):

    url = '/p/%s/admin/ext/import/github-wiki/' % test_project_with_wiki

    @with_wiki
    def test_index(self):
        r = self.app.get(self.url)
        self.assertIsNotNone(r.html.find(attrs=dict(name='gh_user_name')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='gh_project_name')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='mount_label')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='mount_point')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='tool_option', value='import_history')))

    @with_wiki
    @patch('forgeimporters.github.wiki.import_tool')
    def test_create(self, import_tool):
        params = dict(
            gh_user_name='spooky',
            gh_project_name='mulder',
            mount_point='gh-wiki',
            mount_label='GitHub Wiki',
            tool_option='import_history')
        r = self.app.post(self.url + 'create', params, status=302)
        self.assertEqual(r.location, 'http://localhost/p/%s/admin/' % test_project_with_wiki)
        args = import_tool.post.call_args[1]
        self.assertEqual(u'GitHub Wiki', args['mount_label'])
        self.assertEqual(u'gh-wiki', args['mount_point'])
        self.assertEqual(u'mulder', args['project_name'])
        self.assertEqual(u'spooky', args['user_name'])
        self.assertEqual(u'import_history', args['tool_option'])

        # without history
        params.pop('tool_option')
        r = self.app.post(self.url + 'create', params, status=302)
        self.assertEqual(r.location, 'http://localhost/p/%s/admin/' % test_project_with_wiki)
        args = import_tool.post.call_args[1]
        self.assertEqual(u'GitHub Wiki', args['mount_label'])
        self.assertEqual(u'gh-wiki', args['mount_point'])
        self.assertEqual(u'mulder', args['project_name'])
        self.assertEqual(u'spooky', args['user_name'])
        self.assertEqual(u'', args['tool_option'])
