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

from ... import github


class TestGitHubProjectExtractor(TestCase):
    def setUp(self):
        import json
        from StringIO import StringIO
        self.extractor = github.GitHubProjectExtractor('testproject')
        d = dict(description='project description',
                homepage='http://example.com')
        self.extractor.urlopen = lambda url: StringIO(json.dumps(d))

    def test_get_summary(self):
        self.assertEqual(self.extractor.get_summary(), 'project description')

    def test_get_homepage(self):
        self.assertEqual(self.extractor.get_homepage(), 'http://example.com')
