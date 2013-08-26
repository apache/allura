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

from forgeimporters.github.code import GitHubRepoImporter


class TestGitHubRepoImporter(TestCase):

    def _make_project(self, gh_proj_name=None):
        project = Mock()
        project.get_tool_data.side_effect = lambda *args: gh_proj_name
        return project

    @patch('forgeimporters.github.code.g')
    @patch('forgeimporters.github.code.GitHubProjectExtractor')
    def test_import_tool_happy_path(self, ghpe, g):
        ghpe.return_value.get_repo_url.return_value = 'http://remote/clone/url/'
        p = self._make_project(gh_proj_name='myproject')
        GitHubRepoImporter().import_tool(p, Mock(name='c.user'), project_name='project_name', user_name='testuser')
        p.install_app.assert_called_once_with(
            'Git',
            mount_point='code',
            mount_label='Code',
            init_from_url='http://remote/clone/url/')
        g.post_event.assert_called_once_with('project_updated')
