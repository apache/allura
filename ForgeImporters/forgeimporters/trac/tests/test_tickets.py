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

from allura.tests import TestController
from allura.tests.decorators import with_tracker

from forgeimporters.trac.tickets import (
    TracTicketImporter,
    TracTicketImportController,
    )


class TestTracTicketImporter(TestCase):
    @patch('forgeimporters.trac.tickets.session')
    @patch('forgeimporters.trac.tickets.g')
    @patch('forgeimporters.trac.tickets.import_tracker')
    @patch('forgeimporters.trac.tickets.AlluraImportApiClient')
    @patch('forgeimporters.trac.tickets.datetime')
    @patch('forgeimporters.trac.tickets.ApiTicket')
    @patch('forgeimporters.trac.tickets.TracExport')
    def test_import_tool(self, TracExport, ApiTicket, dt, ApiClient, import_tracker, g, session):
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        dt.utcnow.return_value = now
        user_map = {"orig_user":"new_user"}
        importer = TracTicketImporter()
        app = Mock(name='ForgeTrackerApp')
        project = Mock(name='Project', shortname='myproject')
        project.install_app.return_value = app
        user = Mock(name='User', _id='id')
        with patch.dict('forgeimporters.trac.tickets.config', {'base_url': 'foo'}):
            res = importer.import_tool(project, user,
                    mount_point='bugs',
                    mount_label='Bugs',
                    trac_url='http://example.com/trac/url',
                    user_map=json.dumps(user_map),
                    )
        self.assertEqual(res, app)
        project.install_app.assert_called_once_with(
                'Tickets', mount_point='bugs', mount_label='Bugs')
        TracExport.return_value = []
        TracExport.assert_called_once_with('http://example.com/trac/url/')
        ApiTicket.assert_called_once_with(
                user_id=user._id,
                capabilities={"import": ["Projects", "myproject"]},
                expires=now + timedelta(minutes=60))
        api_client = ApiClient.return_value
        import_tracker.assert_called_once_with(
                api_client, 'myproject', 'bugs',
                {"user_map": user_map}, '[]',
                validate=False)
        g.post_event.assert_called_once_with('project_updated')

    @patch('forgeimporters.trac.tickets.session')
    @patch('forgeimporters.trac.tickets.h')
    @patch('forgeimporters.trac.tickets.TracExport')
    def test_import_tool_failure(self, TracExport, h, session):
        importer = TracTicketImporter()
        app = Mock(name='ForgeTrackerApp')
        project = Mock(name='Project', shortname='myproject')
        project.install_app.return_value = app
        user = Mock(name='User', _id='id')
        TracExport.side_effect = ValueError

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
        TrackerAdminController._importer = TracTicketImportController()

    @with_tracker
    def test_index(self):
        r = self.app.get('/p/test/admin/bugs/_importer/')
        self.assertIsNotNone(r.html.find(attrs=dict(name="trac_url")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_label")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_point")))

    @with_tracker
    @patch('forgeimporters.trac.tickets.import_tool')
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
