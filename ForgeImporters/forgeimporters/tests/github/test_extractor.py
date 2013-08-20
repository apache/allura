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

import mock

from ... import github


class TestGitHubProjectExtractor(TestCase):
    def setUp(self):
        self._p_urlopen = mock.patch.object(github.urllib2, 'urlopen')
        self._p_json = mock.patch.object(github.json, 'loads')
        self.urlopen = self._p_urlopen.start()
        self.json = self._p_json.start()
        self.project = mock.Mock(name='project')
        self.project.get_tool_data.return_value = 'testproject'

    def tearDown(self):
        self._p_urlopen.stop()
        self._p_json.stop()


    def test_init(self):
        extractor = github.GitHubProjectExtractor(self.project, 'testproject', 'project_info')
        self.urlopen.assert_called_once_with('https://api.github.com/repos/testproject')
        self.assertEqual(extractor.project, self.project)

    def test_get_summary(self):
        extractor = github.GitHubProjectExtractor(self.project, 'testproject', 'project_info')
        extractor.page = {'description': 'test summary'}
        extractor.get_summmary()
        self.assertEqual(self.project.summary, 'test summary')
