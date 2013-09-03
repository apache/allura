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
            ghpe.return_value.get_wiki_url.return_value = "http://testwiki.com"
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

    @patch('forgeimporters.github.wiki.GitHubWikiImporter.get_wiki_pages_form_git')
    def test_get_wiki_pages(self, get_wiki_pages):
        get_wiki_pages.return_value = {
            "Home_creole.creole": "**TEST**",
            "Home_md.md": "# TEST",
            "Home.rest": "test"
        }
        data = GitHubWikiImporter().get_wiki_pages("http://test.git")
        assert_equal(data['Home_creole'], '<p><strong>TEST</strong></p>\n')
        assert_equal(data['Home_md'], '<div class="markdown_content"><h1 id="test">TEST</h1></div>')
        assert_equal(data['Home'], '<div class="document">\n<p>test</p>\n</div>\n')
