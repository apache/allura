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

import datetime

from unittest import TestCase
from nose.tools import assert_equal
from mock import Mock, patch

from forgeimporters.github.wiki import GitHubWikiImporter
from alluratest.controller import setup_basic_test


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

    def test_get_blobs(self):
        wiki = GitHubWikiImporter().get_blobs(self.commit2)
        assert_equal(wiki['Home'][0], '<div class="markdown_content"><h1 id="test-message">test message</h1></div>')
        assert_equal(wiki['Home'][1], datetime.datetime(2009, 10, 23, 9, 50, 46))
        assert_equal(wiki['Home2'][0], '<p><strong>test message</strong></p>\n')
        assert_equal(wiki['Home3'][0], '<div class="document">\n<p>test message</p>\n</div>\n')

    @patch('forgeimporters.github.wiki.git.Repo')
    @patch('forgeimporters.github.wiki.mkdtemp')
    def test_clone_from(self, path, repo):
        with patch('forgeimporters.github.wiki.rmtree'):
            path.return_value = 'temp_path'
            GitHubWikiImporter().get_wiki_pages('wiki_url')
            repo.clone_from.assert_called_with('wiki_url', to_path='temp_path', bare=True)

    @patch('forgeimporters.github.wiki.git.Repo._clone')
    def test_get_commits(self, clone):
        repo = clone.return_value
        repo.iter_commits.return_value = [self.commit1, self.commit2]
        wiki = GitHubWikiImporter().get_wiki_pages('wiki_url')
        assert_equal(len(wiki), 2)
        assert_equal(wiki[0]['Home'][0], '<div class="markdown_content"><h1 id="test-message">test message</h1></div>')
        assert_equal(wiki[0]['Home2'][0], '<p><strong>test message</strong></p>\n')
        assert_equal(wiki[0]['Home3'][0], '<div class="document">\n<p>test message</p>\n</div>\n')
        assert_equal(len(wiki[0]), 3)

        assert_equal(wiki[1]['Home'][0], '<div class="markdown_content"><h1 id="test-message">test message</h1></div>')
        assert_equal(len(wiki[1]), 1)
