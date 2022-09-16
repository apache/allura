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
from io import BytesIO
import six.moves.urllib.parse
import six.moves.urllib.request
import six.moves.urllib.error

from mock import patch, Mock

from ... import github



class TestGitHubProjectExtractor(TestCase):
    PROJECT_INFO = {
        'description': 'project description',
        'homepage': 'http://example.com',
        'has_wiki': True,
    }
    CLOSED_ISSUES_LIST = [
        {'number': 1},
        {'number': 2},
    ]
    OPENED_ISSUES_LIST = [
        {'number': 3},
        {'number': 4},
        {'number': 5},
    ]
    OPENED_ISSUES_LIST_PAGE2 = [
        {'number': 6},
        {'number': 7},
        {'number': 8},
    ]
    ISSUE_COMMENTS = ['hello', 'mocked_comment']
    ISSUE_COMMENTS_PAGE2 = ['hello2', 'mocked_comment2']
    ISSUE_EVENTS = [
        {'event': 'closed'},
        {'event': 'reopened'},
    ]
    ISSUE_EVENTS_PAGE2 = [
        {'event': 'assigned'},
        {'event': 'not-supported-event'},
    ]

    def mocked_urlopen(self, url):
        headers = {}
        if url.endswith('/test_project'):
            response = BytesIO(json.dumps(self.PROJECT_INFO).encode('utf-8'))
        elif url.endswith('/issues?state=closed'):
            response = BytesIO(json.dumps(self.CLOSED_ISSUES_LIST).encode('utf-8'))
        elif url.endswith('/issues?state=open'):
            response = BytesIO(json.dumps(self.OPENED_ISSUES_LIST).encode('utf-8'))
            headers = {'Link': '</issues?state=open&page=2>; rel="next"'}
        elif url.endswith('/issues?state=open&page=2'):
            response = BytesIO(json.dumps(self.OPENED_ISSUES_LIST_PAGE2).encode('utf-8'))
        elif url.endswith('/comments'):
            response = BytesIO(json.dumps(self.ISSUE_COMMENTS).encode('utf-8'))
            headers = {'Link': '</comments?page=2>; rel="next"'}
        elif url.endswith('/comments?page=2'):
            response = BytesIO(json.dumps(self.ISSUE_COMMENTS_PAGE2).encode('utf-8'))
        elif url.endswith('/events'):
            response = BytesIO(json.dumps(self.ISSUE_EVENTS).encode('utf-8'))
            headers = {'Link': '</events?page=2>; rel="next"'}
        elif url.endswith('/events?page=2'):
            response = BytesIO(json.dumps(self.ISSUE_EVENTS_PAGE2).encode('utf-8'))

        response.info = lambda: headers
        return response

    def setup_method(self, method):
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
        all_issues = list(zip((1, 2), self.CLOSED_ISSUES_LIST))
        all_issues += list(zip((3, 4, 5), self.OPENED_ISSUES_LIST))
        all_issues += list(zip((6, 7, 8), self.OPENED_ISSUES_LIST_PAGE2))
        self.assertEqual(issues, all_issues)

    def test_iter_comments(self):
        mock_issue = {'comments_url': '/issues/1/comments'}
        comments = list(self.extractor.iter_comments(mock_issue))
        self.assertEqual(comments, self.ISSUE_COMMENTS +
                         self.ISSUE_COMMENTS_PAGE2)

    def test_iter_events(self):
        mock_issue = {'events_url': '/issues/1/events'}
        events = list(self.extractor.iter_events(mock_issue))
        self.assertEqual(events, self.ISSUE_EVENTS +
                         self.ISSUE_EVENTS_PAGE2[:1])

    def test_has_wiki(self):
        assert self.extractor.has_wiki()

    def test_get_wiki_url(self):
        self.assertEqual(self.extractor.get_page_url('wiki_url'),
                         'https://github.com/test_project.wiki')

    @patch('forgeimporters.base.h.urlopen')
    def test_urlopen(self, urlopen):
        e = github.GitHubProjectExtractor('test_project')
        url = 'https://github.com/u/p/'
        e.urlopen(url)
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_full_url(), url)

        user = Mock()
        user.get_tool_data.return_value = 'abc'
        e = github.GitHubProjectExtractor('test_project', user=user)
        e.urlopen(url)
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_full_url(), url)
        assert request.headers['User-agent']
        self.assertEqual(request.unredirected_hdrs['Authorization'], 'token abc')

    @patch('forgeimporters.base.h.urlopen')
    @patch('forgeimporters.github.time.sleep')
    @patch('forgeimporters.github.log')
    def test_urlopen_rate_limit(self, log, sleep, urlopen):
        limit_exceeded_headers = {
            'X-RateLimit-Limit': '10',
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': '1382693522',
        }
        response_limit_exceeded = BytesIO(b'{}')
        response_limit_exceeded.info = lambda: limit_exceeded_headers
        response_ok = BytesIO(b'{}')
        response_ok.info = lambda: {}
        urlopen.side_effect = [response_limit_exceeded, response_ok]
        e = github.GitHubProjectExtractor('test_project')
        e.get_page('http://example.com/')
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(urlopen.call_count, 2)
        log.warn.assert_called_once_with(
            'Rate limit exceeded (10 requests/hour). '
            'Sleeping until 2013-10-25 09:32:02 UTC'
        )
        sleep.reset_mock()
        urlopen.reset_mock()
        log.warn.reset_mock()
        response_ok = BytesIO(b'{}')
        response_ok.info = lambda: {}
        urlopen.side_effect = [response_ok]
        e.get_page('http://example.com/2')
        self.assertEqual(sleep.call_count, 0)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(log.warn.call_count, 0)

    @patch('forgeimporters.base.h.urlopen')
    @patch('forgeimporters.github.time.sleep')
    @patch('forgeimporters.github.log')
    def test_urlopen_rate_limit_403(self, log, sleep, urlopen):
        '''Test that urlopen catches 403 which may happen if limit exceeded by another task'''
        limit_exceeded_headers = {
            'X-RateLimit-Limit': '10',
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': '1382693522',
        }

        def urlopen_side_effect(*a, **kw):
            mock_resp = BytesIO(b'{}')
            mock_resp.info = lambda: {}
            urlopen.side_effect = [mock_resp]
            raise six.moves.urllib.error.HTTPError(
                'url', 403, 'msg', limit_exceeded_headers, BytesIO(b'{}'))
        urlopen.side_effect = urlopen_side_effect
        e = github.GitHubProjectExtractor('test_project')
        e.get_page('http://example.com/')
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(urlopen.call_count, 2)
        log.warn.assert_called_once_with(
            'Rate limit exceeded (10 requests/hour). '
            'Sleeping until 2013-10-25 09:32:02 UTC'
        )

    @patch.object(github.requests, 'head')
    def test_check_readable(self, head):
        head.return_value.status_code = 200
        assert github.GitHubProjectExtractor('my-project').check_readable()
        head.return_value.status_code = 404
        assert not github.GitHubProjectExtractor('my-project').check_readable()
