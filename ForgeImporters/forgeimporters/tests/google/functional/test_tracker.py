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
import pkg_resources
from functools import wraps
from datetime import datetime

from BeautifulSoup import BeautifulSoup
import mock
from ming.orm import ThreadLocalORMSession
from pylons import tmpl_context as c
from IPython.testing.decorators import module_not_available, skipif

from alluratest.controller import setup_basic_test
from allura.tests.decorators import without_module
from allura import model as M
from forgetracker import model as TM
from .... import google
from ....google import tracker


class TestGCTrackerImporter(TestCase):
    def _make_extractor(self, html):
        with mock.patch.object(google, 'urllib2') as urllib2:
            urllib2.urlopen.return_value = ''
            extractor = google.GoogleCodeProjectExtractor('my-project', 'project_info')
        extractor.page = BeautifulSoup(html)
        extractor.url = "http://test/issue/?id=1"
        return extractor

    def _make_ticket(self, issue):
        self.assertIsNone(self.project.app_instance('test-issue'))
        with mock.patch.object(google, 'urllib2') as urllib2,\
             mock.patch.object(google.tracker, 'GoogleCodeProjectExtractor') as GPE:
            urllib2.urlopen = lambda url: mock.Mock(read=lambda: url)
            GPE.iter_issues.return_value = [issue]
            gti = google.tracker.GoogleCodeTrackerImporter()
            gti.import_tool(self.project, self.user, 'test-issue-project', mount_point='test-issue')
        c.app = self.project.app_instance('test-issue')
        query = TM.Ticket.query.find({'app_config_id': c.app.config._id})
        self.assertEqual(query.count(), 1)
        ticket = query.all()[0]
        return ticket

    def setUp(self, *a, **kw):
        super(TestGCTrackerImporter, self).setUp(*a, **kw)
        setup_basic_test()
        self.empty_issue = self._make_extractor(open(pkg_resources.resource_filename('forgeimporters', 'tests/data/google/empty-issue.html')).read())
        self.test_issue = self._make_extractor(open(pkg_resources.resource_filename('forgeimporters', 'tests/data/google/test-issue.html')).read())
        c.project = self.project = M.Project.query.get(shortname='test')
        c.user = self.user = M.User.query.get(username='test-admin')

    def test_empty_issue(self):
        ticket = self._make_ticket(self.empty_issue)
        self.assertEqual(ticket.summary, 'Empty Issue')
        self.assertEqual(ticket.description, '*Originally created by:* [john...@gmail.com](http://code.google.com/u/101557263855536553789/)\n\nEmpty')
        self.assertEqual(ticket.status, '')
        self.assertEqual(ticket.milestone, '')
        self.assertEqual(ticket.custom_fields, {})

    @without_module('html2text')
    def test_issue_basic_fields(self):
        anon = M.User.anonymous()
        ticket = self._make_ticket(self.test_issue)
        self.assertEqual(ticket.reported_by, anon)
        self.assertIsNone(ticket.assigned_to_id)
        self.assertEqual(ticket.summary, 'Test Issue')
        self.assertEqual(ticket.description,
                '*Originally created by:* [john...@gmail.com](http://code.google.com/u/101557263855536553789/)\n'
                '*Originally owned by:* [john...@gmail.com](http://code.google.com/u/101557263855536553789/)\n'
                '\n'
                'Test \\*Issue\\* for testing\n'
                '\n'
                '&nbsp; 1\\. Test List\n'
                '&nbsp; 2\\. Item\n'
                '\n'
                '\\*\\*Testing\\*\\*\n'
                '\n'
                ' \\* Test list 2\n'
                ' \\* Item\n'
                '\n'
                '\\# Test Section\n'
                '\n'
                '&nbsp;&nbsp;&nbsp; p = source\\.test\\_issue\\.post\\(\\)\n'
                '&nbsp;&nbsp;&nbsp; p\\.count = p\\.count \\*5 \\#\\* 6\n'
                '\n'
                'That\'s all'
            )
        self.assertEqual(ticket.status, 'Started')
        self.assertEqual(ticket.created_date, datetime(2013, 8, 8, 15, 33, 52))
        self.assertEqual(ticket.mod_date, datetime(2013, 8, 8, 15, 36, 57))
        self.assertEqual(ticket.custom_fields, {
                '_priority': 'Medium',
                '_opsys': 'All, OSX, Windows',
                '_component': 'Logic',
                '_type': 'Defect',
                '_milestone': 'Release1.0'
            })
        self.assertEqual(ticket.labels, ['Performance', 'Security'])

    @skipif(module_not_available('html2text'))
    def test_html2text_escaping(self):
        ticket = self._make_ticket(self.test_issue)
        self.assertEqual(ticket.description,
                '*Originally created by:* [john...@gmail.com](http://code.google.com/u/101557263855536553789/)\n'
                '*Originally owned by:* [john...@gmail.com](http://code.google.com/u/101557263855536553789/)\n'
                '\n'
                'Test \\*Issue\\* for testing\n'
                '\n'
                '&nbsp; 1. Test List\n'
                '&nbsp; 2. Item\n'
                '\n'
                '\\*\\*Testing\\*\\*\n'
                '\n'
                ' \\* Test list 2\n'
                ' \\* Item\n'
                '\n'
                '\\# Test Section\n'
                '\n'
                '&nbsp;&nbsp;&nbsp; p = source.test\\_issue.post\\(\\)\n'
                '&nbsp;&nbsp;&nbsp; p.count = p.count \\*5 \\#\\* 6\n'
                '\n'
                'That\'s all'
            )

    def _assert_attachments(self, actual, *expected):
        self.assertEqual(actual.count(), len(expected))
        atts = set((a.filename, a.content_type, a.rfile().read()) for a in actual)
        self.assertEqual(atts, set(expected))

    def test_attachements(self):
        ticket = self._make_ticket(self.test_issue)
        self._assert_attachments(ticket.attachments,
                ('at1.txt', 'text/plain', 'http://allura-google-importer.googlecode.com/issues/attachment?aid=70000000&name=at1.txt&token=3REU1M3JUUMt0rJUg7ldcELt6LA%3A1376059941255'),
                ('at2.txt', 'text/plain', 'http://allura-google-importer.googlecode.com/issues/attachment?aid=70000001&name=at2.txt&token=C9Hn4s1-g38hlSggRGo65VZM1ys%3A1376059941255'),
            )

    @without_module('html2text')
    def test_comments(self):
        anon = M.User.anonymous()
        ticket = self._make_ticket(self.test_issue)
        actual_comments = ticket.discussion_thread.find_posts()
        expected_comments = [
                {
                    'timestamp': datetime(2013, 8, 8, 15, 35, 15),
                    'text': (
                            '*Originally posted by:* [john...@gmail.com](http://code.google.com/u/101557263855536553789/)\n'
                            '\n'
                            'Test \\*comment\\* is a comment\n'
                            '\n'
                            '**Labels:** -OpSys-Linux OpSys-Windows\n'
                            '**Status:** Started'
                        ),
                    'attachments': [
                            ('at2.txt', 'text/plain', 'http://allura-google-importer.googlecode.com/issues/attachment?aid=60001000&name=at2.txt&token=JOSo4duwaN2FCKZrwYOQ-nx9r7U%3A1376001446667'),
                        ],
                },
                {
                    'timestamp': datetime(2013, 8, 8, 15, 35, 34),
                    'text': (
                            '*Originally posted by:* [john...@gmail.com](http://code.google.com/u/101557263855536553789/)\n'
                            '\n'
                            'Another comment\n\n'
                        ),
                },
                {
                    'timestamp': datetime(2013, 8, 8, 15, 36, 39),
                    'text': (
                            '*Originally posted by:* [john...@gmail.com](http://code.google.com/u/101557263855536553789/)\n'
                            '\n'
                            'Last comment\n\n'
                        ),
                    'attachments': [
                            ('at4.txt', 'text/plain', 'http://allura-google-importer.googlecode.com/issues/attachment?aid=60003000&name=at4.txt&token=6Ny2zYHmV6b82dqxyoiH6HUYoC4%3A1376001446667'),
                            ('at1.txt', 'text/plain', 'http://allura-google-importer.googlecode.com/issues/attachment?aid=60003001&name=at1.txt&token=NS8aMvWsKzTAPuY2kniJG5aLzPg%3A1376001446667'),
                        ],
                },
                {
                    'timestamp': datetime(2013, 8, 8, 15, 36, 57),
                    'text': (
                            '*Originally posted by:* [john...@gmail.com](http://code.google.com/u/101557263855536553789/)\n'
                            '\n'
                            'Oh, I forgot one\n'
                            '\n'
                            '**Labels:** OpSys-OSX'
                        ),
                },
            ]
        self.assertEqual(len(actual_comments), len(expected_comments))
        for actual, expected in zip(actual_comments, expected_comments):
            self.assertEqual(actual.author(), anon)
            self.assertEqual(actual.timestamp, expected['timestamp'])
            self.assertEqual(actual.text, expected['text'])
            if 'attachments' in expected:
                self._assert_attachments(actual.attachments, *expected['attachments'])

    def test_globals(self):
        globals = self._make_ticket(self.test_issue).globals
        self.assertItemsEqual(globals.custom_fields, [
                {
                    'label': 'Milestone',
                    'name': '_milestone',
                    'type': 'milestone',
                    'options': '',
                    'milestones': [
                            {'name': 'Release1.0', 'due_date': None, 'complete': False},
                        ],
                },
                {
                    'label': 'Type',
                    'name': '_type',
                    'type': 'select',
                    'options': 'Defect',
                },
                {
                    'label': 'Priority',
                    'name': '_priority',
                    'type': 'select',
                    'options': 'Medium',
                },
                {
                    'label': 'OpSys',
                    'name': '_opsys',
                    'type': 'string',
                    'options': '',
                },
                {
                    'label': 'Component',
                    'name': '_component',
                    'type': 'string',
                    'options': '',
                },
            ])
