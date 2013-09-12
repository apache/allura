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
from allura.tests import TestController

class TestGitHubImportController(TestController, TestCase):

    def test_index(self):
        r = self.app.get('/p/import_project/github/')
        assert 'GitHub Project Importer' in r
        assert '<input id="user_name" name="user_name" value="" autofocus/>' in r
        assert '<input id="project_name" name="project_name" value="" />' in r
        assert '<input id="project_shortname" name="project_shortname" value=""/>' in r

    def test_login_overlay(self):
        r = self.app.get('/p/import_project/github/', extra_environ=dict(username='*anonymous'))
        self.assertIn('GitHub Project Importer', r)
        self.assertIn('Login Required', r)

        r = self.app.post('/p/import_project/github/process', extra_environ=dict(username='*anonymous'), status=302)
        self.assertIn('/auth/', r.location)
