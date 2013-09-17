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

# Can't use cStringIO here, because we cannot set attributes or subclass it,
# and this is needed in mocked_urlopen below
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
        {u'number': 4},
        {u'number': 5},
    ]
    OPENED_ISSUES_LIST_PAGE2 = [
        {u'number': 6},
        {u'number': 7},
        {u'number': 8},
    ]
    ISSUE_COMMENTS = [u'hello', u'mocked_comment']
    ISSUE_COMMENTS_PAGE2 = [u'hello2', u'mocked_comment2']
    ISSUE_EVENTS = [
        {u'event': u'closed'},
        {u'event': u'reopened'},
    ]
    ISSUE_EVENTS_PAGE2 = [
        {u'event': u'assigned'},
        {u'event': u'not-supported-event'},
    ]

    def mocked_urlopen(self, url):
        headers = {}
        if url.endswith('/test_project'):
            response = StringIO(json.dumps(self.PROJECT_INFO))
        elif url.endswith('/issues?state=closed'):
            response = StringIO(json.dumps(self.CLOSED_ISSUES_LIST))
        elif url.endswith('/issues?state=opened'):
            response = StringIO(json.dumps(self.OPENED_ISSUES_LIST))
            headers = {'Link': '</issues?state=opened&page=2>; rel="next"'}
        elif url.endswith('/issues?state=opened&page=2'):
            response = StringIO(json.dumps(self.OPENED_ISSUES_LIST_PAGE2))
        elif url.endswith('/comments'):
            response = StringIO(json.dumps(self.ISSUE_COMMENTS))
            headers = {'Link': '</comments?page=2>; rel="next"'}
        elif url.endswith('/comments?page=2'):
            response = StringIO(json.dumps(self.ISSUE_COMMENTS_PAGE2))
        elif url.endswith('/events'):
            response = StringIO(json.dumps(self.ISSUE_EVENTS))
            headers = {'Link': '</events?page=2>; rel="next"'}
        elif url.endswith('/events?page=2'):
            response = StringIO(json.dumps(self.ISSUE_EVENTS_PAGE2))

        response.info = lambda: headers
        return response

    def setUp(self):
        self.extractor = github.GitHubProjectExtractor('test_project')
        self.extractor.urlopen = self.mocked_urlopen

    def test_get_next_page_url(self):
        self.assertIsNone(self.extractor.get_next_page_url(None))
        self.assertIsNone(self.extractor.get_next_page_url(''))
        link = '<https://api.github.com/repositories/8560576/issues?state=open&page=2>; rel="next", <https://api.github.com/repositories/8560576/issues?state=open&page=10>; rel="last"'
        self.assertEqual(self.extractor.get_next_page_url(link),
                'https://api.github.com/repositories/8560576/issues?state=open&page=2')

        link = '<https://api.github.com/repositories/8560576/issues?state=open&page=2>; rel="next"'
        self.assertEqual(self.extractor.get_next_page_url(link),
                'https://api.github.com/repositories/8560576/issues?state=open&page=2')

        link = '<https://api.github.com/repositories/8560576/issues?state=open&page=1>; rel="prev"'
        self.assertIsNone(self.extractor.get_next_page_url(link))

    def test_get_summary(self):
        self.assertEqual(self.extractor.get_summary(), 'project description')

    def test_get_homepage(self):
        self.assertEqual(self.extractor.get_homepage(), 'http://example.com')

    def test_iter_issues(self):
        issues = list(self.extractor.iter_issues())
        all_issues = zip((1,2), self.CLOSED_ISSUES_LIST)
        all_issues += zip((3, 4, 5), self.OPENED_ISSUES_LIST)
        all_issues += zip((6, 7, 8), self.OPENED_ISSUES_LIST_PAGE2)
        self.assertEqual(issues, all_issues)

    def test_iter_comments(self):
        mock_issue = {'comments_url': '/issues/1/comments'}
        comments = list(self.extractor.iter_comments(mock_issue))
        self.assertEqual(comments, self.ISSUE_COMMENTS + self.ISSUE_COMMENTS_PAGE2)

    def test_iter_events(self):
        mock_issue = {'events_url': '/issues/1/events'}
        events = list(self.extractor.iter_events(mock_issue))
        self.assertEqual(events, self.ISSUE_EVENTS + self.ISSUE_EVENTS_PAGE2[:1])
