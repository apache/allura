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

from datetime import datetime
from operator import itemgetter
from unittest import TestCase
import mock

from ...google import tracker


class TestTrackerImporter(TestCase):
    @mock.patch.object(tracker, 'g')
    @mock.patch.object(tracker, 'c')
    @mock.patch.object(tracker, 'ThreadLocalORMSession')
    @mock.patch.object(tracker, 'session')
    @mock.patch.object(tracker, 'M')
    @mock.patch.object(tracker, 'TM')
    @mock.patch.object(tracker, 'GoogleCodeProjectExtractor')
    def test_import_tool(self, gpe, TM, M, session, tlos, c, g):
        importer = tracker.GoogleCodeTrackerImporter()
        importer.process_fields = mock.Mock()
        importer.process_labels = mock.Mock()
        importer.process_comments = mock.Mock()
        importer.postprocess_custom_fields = mock.Mock()
        project, user = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        issues = gpe.iter_issues.return_value = [mock.Mock(), mock.Mock()]
        tickets = TM.Ticket.new.side_effect = [mock.Mock(), mock.Mock()]

        importer.import_tool(project, user, project_name='project_name',
                mount_point='mount_point', mount_label='mount_label')

        project.install_app.assert_called_once_with('tickets', 'mount_point', 'mount_label', EnableVoting=True)
        gpe.iter_issues.assert_called_once_with('project_name')
        self.assertEqual(importer.process_fields.call_args_list, [
                mock.call(tickets[0], issues[0]),
                mock.call(tickets[1], issues[1]),
            ])
        self.assertEqual(importer.process_labels.call_args_list, [
                mock.call(tickets[0], issues[0]),
                mock.call(tickets[1], issues[1]),
            ])
        self.assertEqual(importer.process_comments.call_args_list, [
                mock.call(tickets[0], issues[0]),
                mock.call(tickets[1], issues[1]),
            ])
        self.assertEqual(tlos.flush_all.call_args_list, [
                mock.call(),
                mock.call(),
            ])
        self.assertEqual(session.return_value.flush.call_args_list, [
                mock.call(tickets[0]),
                mock.call(tickets[1]),
            ])
        self.assertEqual(session.return_value.expunge.call_args_list, [
                mock.call(tickets[0]),
                mock.call(tickets[1]),
            ])
        g.post_event.assert_called_once_with('project_updated')

    def test_custom_fields(self):
        importer = tracker.GoogleCodeTrackerImporter()
        importer.custom_fields = {}
        importer.custom_field('Foo')
        importer.custom_field('Milestone')
        importer.custom_field('Priority')
        importer.custom_field('Type')
        self.assertEqual(importer.custom_fields, {
                'Foo': {
                        'type': 'string',
                        'label': 'Foo',
                        'name': '_foo',
                        'options': set(),
                    },
                'Milestone': {
                        'type': 'milestone',
                        'label': 'Milestone',
                        'name': '_milestone',
                        'options': set(),
                    },
                'Priority': {
                        'type': 'select',
                        'label': 'Priority',
                        'name': '_priority',
                        'options': set(),
                    },
                'Type': {
                        'type': 'select',
                        'label': 'Type',
                        'name': '_type',
                        'options': set(),
                    },
            })
        importer.custom_fields = {'Foo': {}}
        importer.custom_field('Foo')
        self.assertEqual(importer.custom_fields, {'Foo': {}})

    def test_process_fields(self):
        ticket = mock.Mock()
        issue = mock.Mock(
                get_issue_summary=lambda:'summary',
                get_issue_description=lambda:'my *description* fool',
                get_issue_status=lambda:'status',
                get_issue_created_date=lambda:'created_date',
                get_issue_mod_date=lambda:'mod_date',
                get_issue_creator=lambda:'creator',
                get_issue_owner=lambda:'owner',
            )
        importer = tracker.GoogleCodeTrackerImporter()
        with mock.patch.object(tracker, 'datetime') as dt:
            dt.strptime.side_effect = lambda s,f: s
            importer.process_fields(ticket, issue)
            self.assertEqual(ticket.summary, 'summary')
            self.assertEqual(ticket.description, '*Originally created by:* creator\n*Originally owned by:* owner\n\nmy \*description\* fool')
            self.assertEqual(ticket.status, 'status')
            self.assertEqual(ticket.created_date, 'created_date')
            self.assertEqual(ticket.mod_date, 'mod_date')
            self.assertEqual(dt.strptime.call_args_list, [
                    mock.call('created_date', '%c'),
                    mock.call('mod_date', '%c'),
                ])

    def test_process_labels(self):
        ticket = mock.Mock(custom_fields={}, labels=[])
        issue = mock.Mock(get_issue_labels=lambda:['Foo-Bar', 'Baz', 'Foo-Qux'])
        importer = tracker.GoogleCodeTrackerImporter()
        importer.custom_field = mock.Mock(side_effect=lambda n: {'name': '_%s' % n.lower(), 'options': set()})
        importer.process_labels(ticket, issue)
        self.assertEqual(ticket.labels, ['Baz'])
        self.assertEqual(ticket.custom_fields, {'_foo': 'Bar, Qux'})

    def test_process_comments(self):
        def _author(n):
            a = mock.Mock()
            a.name = 'author%s' % n
            a.link = 'author%s_link' % n
            return a
        ticket = mock.Mock()
        issue = mock.Mock()
        comments = issue.iter_comments.return_value = [
                mock.Mock(
                    author=_author(1),
                    body='text1',
                    annotated_text='annotated1',
                    attachments='attachments1',
                    created_date='Mon Jul 15 00:00:00 2013',
                ),
                mock.Mock(
                    author=_author(2),
                    body='text2',
                    annotated_text='annotated2',
                    attachments='attachments2',
                    created_date='Mon Jul 16 00:00:00 2013',
                ),
            ]
        comments[0].updates.items.return_value = [('Foo:', 'Bar'), ('Baz:', 'Qux')]
        comments[1].updates.items.return_value = []
        posts = ticket.discussion_thread.add_post.side_effect = [
                mock.Mock(),
                mock.Mock(),
            ]
        importer = tracker.GoogleCodeTrackerImporter()
        importer.process_comments(ticket, issue)
        self.assertEqual(ticket.discussion_thread.add_post.call_args_list[0], mock.call(
                text='annotated1',
                timestamp=datetime(2013, 7, 15),
                ignore_security=True,
            ))
        posts[0].add_multiple_attachments.assert_called_once_with('attachments1')
        self.assertEqual(ticket.discussion_thread.add_post.call_args_list[1], mock.call(
                text='annotated2',
                timestamp=datetime(2013, 7, 16),
                ignore_security=True,
            ))
        posts[1].add_multiple_attachments.assert_called_once_with('attachments2')

    @mock.patch.object(tracker, 'c')
    def test_postprocess_custom_fields(self, c):
        importer = tracker.GoogleCodeTrackerImporter()
        importer.open_milestones = set(['m2', 'm3'])
        importer.custom_fields = {
                'Foo': {
                    'name': '_foo',
                    'type': 'string',
                    'options': set(['foo', 'bar']),
                },
                'Milestone': {
                    'name': '_milestone',
                    'type': 'milestone',
                    'options': set(['m3', 'm1', 'm2']),
                },
                'Priority': {
                    'name': '_priority',
                    'type': 'select',
                    'options': set(['foo', 'bar']),
                },
            }
        custom_fields = importer.postprocess_custom_fields()
        self.assertItemsEqual(custom_fields, [
                {
                    'name': '_foo',
                    'type': 'string',
                    'options': '',
                },
                {
                    'name': '_milestone',
                    'type': 'milestone',
                    'options': '',
                    'milestones': [
                        {'name': 'm1', 'due_date': None, 'complete': True},
                        {'name': 'm2', 'due_date': None, 'complete': False},
                        {'name': 'm3', 'due_date': None, 'complete': False},
                    ],
                },
                {
                    'name': '_priority',
                    'type': 'select',
                    'options': 'foo bar',
                },
            ])
