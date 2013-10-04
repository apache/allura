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
from mock import Mock, patch
from ming.orm import ThreadLocalORMSession

from tg import config

from allura.tests import TestController
from allura.tests.decorators import with_tracker

from allura import model as M
from forgeimporters.trac.tickets import (
    TracTicketImporter,
    TracTicketImportController,
    )


class TestTracTicketImporter(TestCase):
    @patch('forgeimporters.trac.tickets.session')
    @patch('forgeimporters.trac.tickets.g')
    @patch('forgeimporters.trac.tickets.AuditLog')
    @patch('forgeimporters.trac.tickets.ImportSupport')
    @patch('forgeimporters.trac.tickets.export')
    def test_import_tool(self, export, ImportSupport, AuditLog, g, session):
        user_map = {"orig_user":"new_user"}
        importer = TracTicketImporter()
        app = Mock(name='ForgeTrackerApp')
        app.config.options.mount_point = 'bugs'
        app.config.options.get = lambda *a: getattr(app.config.options, *a)
        app.url = 'foo'
        project = Mock(name='Project', shortname='myproject')
        project.install_app.return_value = app
        user = Mock(name='User', _id='id')
        export.return_value = []
        res = importer.import_tool(project, user,
                mount_point='bugs',
                mount_label='Bugs',
                trac_url='http://example.com/trac/url',
                user_map=json.dumps(user_map),
                )
        self.assertEqual(res, app)
        project.install_app.assert_called_once_with(
                'Tickets', mount_point='bugs', mount_label='Bugs',
                open_status_names='new assigned accepted reopened',
                closed_status_names='closed',
                import_id={
                        'source': 'Trac',
                        'trac_url': 'http://example.com/trac/url/',
                    })
        export.assert_called_once_with('http://example.com/trac/url/')
        ImportSupport.return_value.perform_import.assert_called_once_with(
                json.dumps(export.return_value),
                json.dumps({
                    "user_map": user_map,
                    "usernames_match": False,
                    }),
                )
        AuditLog.log.assert_called_once_with(
                'import tool bugs from http://example.com/trac/url/',
                project=project, user=user, url='foo')
        g.post_event.assert_called_once_with('project_updated')

    @patch('forgeimporters.trac.tickets.session')
    @patch('forgeimporters.trac.tickets.h')
    @patch('forgeimporters.trac.tickets.export')
    def test_import_tool_failure(self, export, h, session):
        importer = TracTicketImporter()
        app = Mock(name='ForgeTrackerApp')
        project = Mock(name='Project', shortname='myproject')
        project.install_app.return_value = app
        user = Mock(name='User', _id='id')
        export.side_effect = ValueError

        self.assertRaises(ValueError, importer.import_tool, project, user,
                mount_point='bugs',
                mount_label='Bugs',
                trac_url='http://example.com/trac/url',
                user_map=None,
                )

        h.make_app_admin_only.assert_called_once_with(app)


class TestTracTicketImportController(TestController, TestCase):
    def setUp(self):
        """Mount Trac import controller on the Tracker admin controller"""
        super(TestTracTicketImportController, self).setUp()
        from forgetracker.tracker_main import TrackerAdminController
        self.importer = TrackerAdminController._importer = TracTicketImportController()

    @with_tracker
    def test_index(self):
        r = self.app.get('/p/test/admin/bugs/_importer/')
        self.assertIsNotNone(r.html.find(attrs=dict(name="trac_url")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_label")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_point")))

    @with_tracker
    @patch('forgeimporters.base.import_tool')
    def test_create(self, import_tool):
        params = dict(trac_url='http://example.com/trac/url',
                mount_label='mylabel',
                mount_point='mymount',
                )
        r = self.app.post('/p/test/admin/bugs/_importer/create', params,
                upload_files=[('user_map', 'myfile', '{"orig_user": "new_user"}')],
                status=302)
        self.assertEqual(r.location, 'http://localhost/p/test/admin/')
        self.assertEqual(u'mymount', import_tool.post.call_args[1]['mount_point'])
        self.assertEqual(u'mylabel', import_tool.post.call_args[1]['mount_label'])
        self.assertEqual('{"orig_user": "new_user"}', import_tool.post.call_args[1]['user_map'])
        self.assertEqual(u'http://example.com/trac/url', import_tool.post.call_args[1]['trac_url'])

    @with_tracker
    @patch('forgeimporters.base.import_tool')
    def test_create_limit(self, import_tool):
        project = M.Project.query.get(shortname='test')
        project.set_tool_data('TracTicketImporter', pending=1)
        ThreadLocalORMSession.flush_all()
        params = dict(trac_url='http://example.com/trac/url',
                mount_label='mylabel',
                mount_point='mymount',
                )
        r = self.app.post('/p/test/admin/bugs/_importer/create', params,
                upload_files=[('user_map', 'myfile', '{"orig_user": "new_user"}')],
                status=302).follow()
        self.assertIn('Please wait and try again', r)
        self.assertEqual(import_tool.post.call_count, 0)
