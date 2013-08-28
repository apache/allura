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

import json
from unittest import TestCase

from ... import github

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO




class TestGitHubProjectExtractor(TestCase):
    PROJECT_INFO = {
        'description': 'project description',
        'homepage': 'http://example.com',
    }
    CLOSED_ISSUES_LIST = [
        {u'number': 1},
        {u'number': 2},
    ]
    OPENED_ISSUES_LIST = [
        {u'number': 3},
    ]
    ISSUE_COMMENTS = [u'hello', u'mocked_comment']

    def mocked_urlopen(self, url):
        if url.endswith('/test_project'):
            return StringIO(json.dumps(self.PROJECT_INFO))
        elif url.endswith('/issues?state=closed'):
            return StringIO(json.dumps(self.CLOSED_ISSUES_LIST))
        elif url.endswith('/issues?state=opened'):
            return StringIO(json.dumps(self.OPENED_ISSUES_LIST))
        elif url.endswith('/comments'):
            return StringIO(json.dumps(self.ISSUE_COMMENTS))

    def setUp(self):
        self.extractor = github.GitHubProjectExtractor('test_project')
        self.extractor.urlopen = self.mocked_urlopen

    def test_get_summary(self):
        self.assertEqual(self.extractor.get_summary(), 'project description')

    def test_get_homepage(self):
        self.assertEqual(self.extractor.get_homepage(), 'http://example.com')

    def test_iter_issues(self):
        issues = list(self.extractor.iter_issues())
        all_issues = zip((1,2), self.CLOSED_ISSUES_LIST)
        all_issues.append((3, self.OPENED_ISSUES_LIST[0]))
        self.assertEqual(issues, all_issues)

    def test_iter_comments(self):
        mock_issue = {'comments_url': '/issues/1/comments'}
        comments = list(self.extractor.iter_comments(mock_issue))
        self.assertEqual(comments, self.ISSUE_COMMENTS)
