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
from mock import patch

from allura.tests import TestController
from allura.tests.decorators import with_tool

# important to be distinct from 'test' which ForgeTracker uses, so that the tests can run in parallel and not clobber each other
test_project_with_tracker = 'test2'
with_tracker = with_tool(test_project_with_tracker, 'tickets', 'spooky-issues', 'tickets')


class TestGitHubTrackerImportController(TestController, TestCase):

    url = '/p/%s/admin/ext/import/github-tracker/' % test_project_with_tracker

    @with_tracker
    def test_index(self):
        r = self.app.get(self.url)
        self.assertIsNotNone(r.html.find(attrs=dict(name='gh_user_name')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='gh_project_name')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='mount_label')))
        self.assertIsNotNone(r.html.find(attrs=dict(name='mount_point')))

    @with_tracker
    @patch('forgeimporters.github.tracker.import_tool')
    def test_create(self, import_tool):
        params = dict(
            gh_user_name='spooky',
            gh_project_name='mulder',
            mount_point='issues',
            mount_label='Issues')
        r = self.app.post(self.url + 'create', params, status=302)
        self.assertEqual(r.location, 'http://localhost/p/%s/admin/' % test_project_with_tracker)
        self.assertEqual(u'Issues', import_tool.post.call_args[1]['mount_label'])
        self.assertEqual(u'issues', import_tool.post.call_args[1]['mount_point'])
        self.assertEqual(u'mulder', import_tool.post.call_args[1]['project_name'])
        self.assertEqual(u'spooky', import_tool.post.call_args[1]['user_name'])
