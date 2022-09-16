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
from unittest import TestCase

import mock
from ming.odm import ThreadLocalORMSession
import webtest

from allura.tests import TestController
from allura.tests.decorators import with_tracker

from allura import model as M
from forgeimporters.forge import tracker

from forgeimporters.forge import alluraImporter


class TestTrackerImporter(TestCase):

    def setup_method(self, method):
        # every single test method here creates an importer and ToolImporterMeta uses 'g'
        self.patcher_g = mock.patch('forgeimporters.base.g', mock.MagicMock())
        self.patcher_g.start()

    def teardown_method(self, method):
        self.patcher_g.stop()

    @mock.patch.object(tracker, 'File')
    @mock.patch.object(tracker.h, 'make_app_admin_only')
    @mock.patch.object(tracker, 'g')
    @mock.patch.object(tracker, 'c')
    @mock.patch.object(tracker, 'ThreadLocalORMSession')
    @mock.patch.object(tracker, 'session')
    @mock.patch.object(tracker, 'M')
    @mock.patch.object(tracker, 'TM')
    def test_import_tool(self, TM, M, session, tlos, c, g, mao, File):
        importer = tracker.ForgeTrackerImporter()
        importer._load_json = mock.Mock(return_value={
            'tracker_config': {
                '_id': 'orig_id',
                'options': {
                    'foo': 'bar',
                },
            },
            'open_status_names': 'open statuses',
            'closed_status_names': 'closed statuses',
            'custom_fields': 'fields',
            'saved_bins': 'bins',
            'tickets': [
                {
                    'reported_by': 'rb1',
                    'assigned_to': 'at1',
                    'attachments': [{'url': 'u1'}, {'url': 'u2'}],
                    'ticket_num': 1,
                    'description': 'd1',
                    'created_date': '2013-09-01',
                    'mod_date': '2013-09-02',
                    'summary': 's1',
                    'custom_fields': 'cf1',
                    'status': 'st1',
                    'labels': 'l1',
                    'votes_down': 1,
                    'votes_up': 2,
                    'private': False,
                    'discussion_thread': {'posts': 'comments1'},
                },
                {
                    'reported_by': 'rb2',
                    'assigned_to': 'at2',
                    'ticket_num': 100,
                    'attachments': [{'url': 'u3'}, {'url': 'u4'}],
                    'description': 'd2',
                    'created_date': '2013-09-03',
                    'mod_date': '2013-09-04',
                    'summary': 's2',
                    'custom_fields': 'cf2',
                    'status': 'st2',
                    'labels': 'l2',
                    'votes_down': 3,
                    'votes_up': 5,
                    'private': True,
                    'discussion_thread': {'posts': 'comments2'},
                },
            ],
        })
        anonymous = mock.Mock(_id=None, is_anonymous=lambda: True)
        reporter = mock.Mock(is_anonymous=lambda: False)
        author = mock.Mock(is_anonymous=lambda: False)
        importer.get_user = mock.Mock(side_effect=[
            reporter, author,
            anonymous, anonymous,
        ])
        importer.annotate = mock.Mock(
            side_effect=['ad1', 'aad1', 'ad2', 'aad2'])
        importer.process_comments = mock.Mock()
        importer.process_bins = mock.Mock()
        project, user = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        app.config.options.mount_point = 'mount_point'
        app.config.options.import_id = {
            'source': 'Allura',
            'app_config_id': 'orig_id',
        }
        app.config.options.get = lambda *a: getattr(app.config.options, *a)
        app.url = 'foo'
        tickets = TM.Ticket.side_effect = [mock.Mock(), mock.Mock()]
        File.side_effect = ['f1', 'f2', 'f3', 'f4']

        importer.import_tool(project, user,
                             mount_point='mount_point', mount_label='mount_label')

        project.install_app.assert_called_once_with(
            'tickets', 'mount_point', 'mount_label',
            open_status_names='open statuses',
            closed_status_names='closed statuses',
            import_id={
                'source': 'Allura',
                'app_config_id': 'orig_id',
            },
            foo='bar',
        )
        self.assertEqual(importer.annotate.call_args_list, [
            mock.call('d1', author, 'at1', label=' owned'),
            mock.call('ad1', reporter, 'rb1', label=' created'),
            mock.call('d2', anonymous, 'at2', label=' owned'),
            mock.call('ad2', anonymous, 'rb2', label=' created'),
        ])
        self.assertEqual(TM.Ticket.call_args_list, [
            mock.call(
                app_config_id=app.config._id,
                import_id={
                    'source': 'Allura',
                    'app_config_id': 'orig_id',
                    'source_id': 1,
                },
                description='aad1',
                created_date=datetime(2013, 9, 1),
                mod_date=datetime(2013, 9, 2),
                ticket_num=1,
                summary='s1',
                custom_fields='cf1',
                status='st1',
                labels='l1',
                votes_down=1,
                votes_up=2,
                votes=1,
                assigned_to_id=author._id,
            ),
            mock.call(
                app_config_id=app.config._id,
                import_id={
                    'source': 'Allura',
                    'app_config_id': 'orig_id',
                    'source_id': 100,
                },
                description='aad2',
                created_date=datetime(2013, 9, 3),
                mod_date=datetime(2013, 9, 4),
                ticket_num=100,
                summary='s2',
                custom_fields='cf2',
                status='st2',
                labels='l2',
                votes_down=3,
                votes_up=5,
                votes=2,
                assigned_to_id=None,
            ),
        ])
        self.assertEqual(tickets[0].private, False)
        self.assertEqual(tickets[1].private, True)
        self.assertEqual(importer.process_comments.call_args_list, [
            mock.call(tickets[0], 'comments1'),
            mock.call(tickets[1], 'comments2'),
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
        self.assertEqual(app.globals.custom_fields, 'fields')
        importer.process_bins.assert_called_once_with(app, 'bins')
        self.assertEqual(app.globals.last_ticket_num, 100)
        M.AuditLog.log.assert_called_once_with(
            'import tool mount_point from exported Allura JSON',
            project=project, user=user, url='foo')
        g.post_event.assert_called_once_with('project_updated')
        app.globals.invalidate_bin_counts.assert_called_once_with()
        self.assertEqual(File.call_args_list, [
            mock.call('u1'),
            mock.call('u2'),
            mock.call('u3'),
            mock.call('u4'),
        ])
        self.assertEqual(tickets[0].add_multiple_attachments.call_args_list, [
            mock.call(['f1', 'f2'])])
        self.assertEqual(tickets[1].add_multiple_attachments.call_args_list, [
            mock.call(['f3', 'f4']),
        ])

    @mock.patch.object(tracker, 'ThreadLocalORMSession')
    @mock.patch.object(tracker, 'M')
    @mock.patch.object(tracker, 'h')
    def test_import_tool_failure(self, h, M, ThreadLocalORMSession):
        M.session.artifact_orm_session._get.side_effect = ValueError
        project = mock.Mock()
        user = mock.Mock()
        tracker_json = {
            'tracker_config': {'_id': 'orig_id', 'options': {}},
            'open_status_names': 'os',
            'closed_status_names': 'cs',
        }

        importer = tracker.ForgeTrackerImporter()
        importer._load_json = mock.Mock(return_value=tracker_json)
        self.assertRaises(
            ValueError, importer.import_tool, project, user, project_name='project_name',
            mount_point='mount_point', mount_label='mount_label')

        h.make_app_admin_only.assert_called_once_with(
            project.install_app.return_value)

    @mock.patch.object(alluraImporter, 'M')
    def test_get_user(self, M):
        importer = tracker.ForgeTrackerImporter()
        M.User.anonymous.return_value = 'anon'

        M.User.by_username.return_value = 'bar'
        self.assertEqual(importer.get_user('foo'), 'bar')
        self.assertEqual(M.User.anonymous.call_count, 0)

        self.assertEqual(importer.get_user(None), 'anon')
        self.assertEqual(M.User.anonymous.call_count, 1)

        M.User.by_username.return_value = None
        self.assertEqual(importer.get_user('foo'), 'anon')
        self.assertEqual(M.User.anonymous.call_count, 2)

    def test_annotate(self):
        importer = tracker.ForgeTrackerImporter()
        user = mock.Mock(_id=1)
        user.is_anonymous.return_value = False
        self.assertEqual(importer.annotate('foo', user, 'bar'), 'foo')
        user.is_anonymous.return_value = True
        self.assertEqual(importer.annotate('foo', user, 'bar'),
                         '*Originally by:* bar\n\nfoo')
        self.assertEqual(importer.annotate('foo', user, 'nobody'), 'foo')
        self.assertEqual(importer.annotate('foo', user, None), 'foo')

    @mock.patch.object(tracker, 'File')
    @mock.patch.object(tracker, 'c')
    def test_process_comments(self, c, File):
        importer = tracker.ForgeTrackerImporter()
        author = mock.Mock()
        importer.get_user = mock.Mock(return_value=author)
        importer.annotate = mock.Mock(side_effect=['at1', 'at2'])
        ticket = mock.Mock()
        add_post = ticket.discussion_thread.add_post
        ama = add_post.return_value.add_multiple_attachments
        File.side_effect = ['f1', 'f2', 'f3', 'f4']
        comments = [
            {
                'author': 'a1',
                'text': 't1',
                'timestamp': '2013-09-01',
                'attachments': [{'url': 'u1'}, {'url': 'u2'}],
            },
            {
                'author': 'a2',
                'text': 't2',
                'timestamp': '2013-09-02',
                'attachments': [{'url': 'u3'}, {'url': 'u4'}],
            },
        ]

        importer.process_comments(ticket, comments)

        self.assertEqual(importer.get_user.call_args_list,
                         [mock.call('a1'), mock.call('a2')])
        self.assertEqual(importer.annotate.call_args_list, [
            mock.call('t1', author, 'a1'),
            mock.call('t2', author, 'a2'),
        ])
        self.assertEqual(add_post.call_args_list, [
            mock.call(text='at1', ignore_security=True,
                      timestamp=datetime(2013, 9, 1)),
            mock.call(text='at2', ignore_security=True,
                      timestamp=datetime(2013, 9, 2)),
        ])
        self.assertEqual(File.call_args_list, [
            mock.call('u1'),
            mock.call('u2'),
            mock.call('u3'),
            mock.call('u4'),
        ])
        self.assertEqual(ama.call_args_list, [
            mock.call(['f1', 'f2']),
            mock.call(['f3', 'f4']),
        ])

    @mock.patch.object(tracker, 'TM')
    def test_process_bins(self, TM):
        app = mock.Mock()
        app.config._id = 1
        importer = tracker.ForgeTrackerImporter()
        importer.process_bins(app, [{'_id': 1, 'b': 1}, {'b': 2}])
        TM.Bin.query.remove.assert_called_once_with({'app_config_id': 1})
        self.assertEqual(TM.Bin.call_args_list, [
            mock.call(app_config_id=1, b=1),
            mock.call(app_config_id=1, b=2),
        ])


class TestForgeTrackerImportController(TestController, TestCase):

    def setup_method(self, method):
        """Mount Allura importer on the Tracker admin controller"""
        super().setup_method(method)
        from forgetracker.tracker_main import TrackerAdminController
        TrackerAdminController._importer = \
                tracker.ForgeTrackerImportController(tracker.ForgeTrackerImporter())

    @with_tracker
    def test_index(self):
        r = self.app.get('/p/test/admin/bugs/_importer/')
        self.assertIsNotNone(r.html.find(attrs=dict(name="tickets_json")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_label")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_point")))

    @with_tracker
    @mock.patch('forgeimporters.forge.tracker.save_importer_upload')
    @mock.patch('forgeimporters.base.import_tool')
    def test_create(self, import_tool, sui):
        project = M.Project.query.get(shortname='test')
        params = {
            'tickets_json': webtest.Upload('tickets.json', b'{"key": "val"}'),
            'mount_label': 'mylabel',
            'mount_point': 'mymount',
        }
        r = self.app.post('/p/test/admin/bugs/_importer/create', params,
                          status=302)
        self.assertEqual(r.location, 'http://localhost/p/test/admin/')
        sui.assert_called_once_with(project, 'tickets.json', '{"key": "val"}')
        self.assertEqual(
            'mymount', import_tool.post.call_args[1]['mount_point'])
        self.assertEqual(
            'mylabel', import_tool.post.call_args[1]['mount_label'])

    @with_tracker
    @mock.patch('forgeimporters.forge.tracker.save_importer_upload')
    @mock.patch('forgeimporters.base.import_tool')
    def test_create_limit(self, import_tool, sui):
        project = M.Project.query.get(shortname='test')
        project.set_tool_data('ForgeTrackerImporter', pending=1)
        ThreadLocalORMSession.flush_all()
        params = {
            'tickets_json': webtest.Upload('tickets.json', b'{"key": "val"}'),
            'mount_label': 'mylabel',
            'mount_point': 'mymount',
        }
        r = self.app.post('/p/test/admin/bugs/_importer/create', params,
                          status=302).follow()
        self.assertIn('Please wait and try again', r)
        self.assertEqual(import_tool.post.call_count, 0)
