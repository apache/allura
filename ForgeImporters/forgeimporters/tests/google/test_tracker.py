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

from operator import itemgetter
from unittest import TestCase
import mock

from ...google import tracker


class TestTrackerImporter(TestCase):
    @mock.patch.object(tracker, 'c')
    @mock.patch.object(tracker, 'session')
    @mock.patch.object(tracker, 'TM')
    @mock.patch.object(tracker, 'GDataAPIExtractor')
    def test_import_tool(self, gdata, TM, session, c):
        importer = tracker.GoogleCodeTrackerImporter()
        importer.process_fields = mock.Mock()
        importer.process_labels = mock.Mock()
        importer.process_comments = mock.Mock()
        importer.postprocess_custom_fields = mock.Mock()
        project, user = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        extractor = gdata.return_value
        issues = extractor.iter_issues.return_value = [mock.Mock(), mock.Mock()]
        tickets = TM.Ticket.new.side_effect = [mock.Mock(), mock.Mock()]
        comments = extractor.iter_comments.side_effect = [mock.Mock(), mock.Mock()]

        importer.import_tool(project, user, project_name='project_name',
                mount_point='mount_point', mount_label='mount_label')

        project.install_app.assert_called_once_with('tracker', 'mount_point', 'mount_label')
        gdata.assert_called_once_with('project_name')
        self.assertEqual(importer.process_fields.call_args_list, [
                mock.call(tickets[0], issues[0]),
                mock.call(tickets[1], issues[1]),
            ])
        self.assertEqual(importer.process_labels.call_args_list, [
                mock.call(tickets[0], issues[0]),
                mock.call(tickets[1], issues[1]),
            ])
        self.assertEqual(importer.process_comments.call_args_list, [
                mock.call(tickets[0], comments[0]),
                mock.call(tickets[1], comments[1]),
            ])
        self.assertEqual(extractor.iter_comments.call_args_list, [
                mock.call(issues[0]),
                mock.call(issues[1]),
            ])
        self.assertEqual(session.call_args_list, [
                mock.call(tickets[0]),
                mock.call(tickets[0]),
                mock.call(tickets[1]),
                mock.call(tickets[1]),
                mock.call(app),
                mock.call(app.globals),
            ])
        self.assertEqual(session.return_value.flush.call_args_list, [
                mock.call(tickets[0]),
                mock.call(tickets[1]),
                mock.call(app),
                mock.call(app.globals),
            ])
        self.assertEqual(session.return_value.expunge.call_args_list, [
                mock.call(tickets[0]),
                mock.call(tickets[1]),
            ])

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
                summary='summary',
                description='description',
                status='status',
                created_date='created_date',
                mod_date='mod_date',
            )
        importer = tracker.GoogleCodeTrackerImporter()
        with mock.patch.object(tracker, 'datetime') as dt:
            dt.strptime.side_effect = lambda s,f: s
            importer.process_fields(ticket, issue)
            self.assertEqual(ticket.summary, 'summary')
            self.assertEqual(ticket.description, 'description')
            self.assertEqual(ticket.status, 'status')
            self.assertEqual(ticket.created_date, 'created_date')
            self.assertEqual(ticket.mod_date, 'mod_date')
            self.assertEqual(dt.strptime.call_args_list, [
                    mock.call('created_date', ''),
                    mock.call('mod_date', ''),
                ])

    def test_process_labels(self):
        ticket = mock.Mock(custom_fields={}, labels=[])
        issue = mock.Mock(labels=['Foo-Bar', 'Baz', 'Foo-Qux'])
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
        comments = [
                mock.Mock(
                    author=_author(1),
                    text='text1',
                    attachments='attachments1',
                ),
                mock.Mock(
                    author=_author(2),
                    text='text2',
                    attachments='attachments2',
                ),
            ]
        comments[0].updates.items.return_value = [('Foo', 'Bar'), ('Baz', 'Qux')]
        comments[1].updates.items.return_value = []
        importer = tracker.GoogleCodeTrackerImporter()
        importer.process_comments(ticket, comments)
        self.assertEqual(ticket.thread.add_post.call_args_list[0], mock.call(
                text='Originally posted by: [author1](author1_link)\n'
                '\n'
                'text1\n'
                '\n'
                '*Foo*: Bar\n'
                '*Baz*: Qux'
            ))
        self.assertEqual(ticket.thread.add_post.call_args_list[1], mock.call(
                text='Originally posted by: [author2](author2_link)\n'
                '\n'
                'text2\n'
                '\n'
            ))
        self.assertEqual(ticket.thread.add_post.return_value.add_multiple_attachments.call_args_list, [
                mock.call('attachments1'),
                mock.call('attachments2'),
            ])

    @mock.patch.object(tracker, 'c')
    def test_postprocess_custom_fields(self, c):
        importer = tracker.GoogleCodeTrackerImporter()
        importer.custom_fields = {
                'Foo': {
                    'name': '_foo',
                    'type': 'string',
                    'options': set(['foo', 'bar']),
                },
                'Milestone': {
                    'name': '_milestone',
                    'type': 'milestone',
                    'options': set(['foo', 'bar']),
                },
                'Priority': {
                    'name': '_priority',
                    'type': 'select',
                    'options': set(['foo', 'bar']),
                },
            }
        importer.postprocess_custom_fields()
        self.assertEqual(sorted(c.app.globals.custom_fields, key=itemgetter('name')), [
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
                        {'name': 'foo', 'due_date': None, 'complete': False},
                        {'name': 'bar', 'due_date': None, 'complete': False},
                    ],
                },
                {
                    'name': '_priority',
                    'type': 'select',
                    'options': 'foo bar',
                },
            ])
