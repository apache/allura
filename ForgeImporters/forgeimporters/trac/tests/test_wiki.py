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
from mock import Mock, patch

from allura.tests import TestController
from allura.tests.decorators import with_wiki

from forgeimporters.trac.wiki import (
    TracWikiImporter,
    TracWikiImportController,
    )


class TestWikiTicketImporter(TestCase):
    @patch('forgeimporters.trac.wiki.session')
    @patch('forgeimporters.trac.wiki.tempfile.NamedTemporaryFile')
    @patch('forgeimporters.trac.wiki.g')
    @patch('forgeimporters.trac.wiki.WikiFromTrac')
    @patch('forgeimporters.trac.wiki.load_data')
    @patch('forgeimporters.trac.wiki.argparse.Namespace')
    @patch('forgeimporters.trac.wiki.WikiExporter')
    @patch('forgeimporters.trac.wiki.ApiTicket')
    @patch('forgeimporters.trac.wiki.datetime')
    def test_import_tool(self, dt, ApiTicket, WikiExporter, Namespace,
            load_data, WikiFromTrac, g, NamedTemporaryFile, session):
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        dt.utcnow.return_value = now
        export_file = NamedTemporaryFile.return_value.__enter__.return_value
        export_file.name = '/my/file'

        importer = TracWikiImporter()
        app = Mock(name='ForgeWikiApp')
        project = Mock(name='Project', shortname='myproject')
        project.install_app.return_value = app
        user = Mock(name='User', _id='id')
        res = importer.import_tool(project, user,
                mount_point='pages',
                mount_label='Pages',
                trac_url='http://example.com/trac/url')
        self.assertEqual(res, app)
        project.install_app.assert_called_once_with(
                'Wiki', mount_point='pages', mount_label='Pages')
        ApiTicket.assert_called_once_with(
                user_id=user._id,
                capabilities={"import": ["Projects", "myproject"]},
                expires=now + timedelta(minutes=60))
        WikiExporter.assert_called_once_with('http://example.com/trac/url/',
                Namespace.return_value)
        WikiExporter.return_value.export.assert_called_once_with(export_file)
        load_data.assert_called_once_with('/my/file',
                WikiFromTrac.parser.return_value, Namespace.return_value)
        g.post_event.assert_called_once_with('project_updated')


class TestTracWikiImportController(TestController, TestCase):
    def setUp(self):
        """Mount Trac import controller on the Wiki admin controller"""
        super(self.__class__, self).setUp()
        from forgewiki.wiki_main import WikiAdminController
        WikiAdminController._importer = TracWikiImportController()

    @with_wiki
    def test_index(self):
        r = self.app.get('/p/test/admin/wiki/_importer/')
        self.assertIsNotNone(r.html.find(attrs=dict(name="trac_url")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_label")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_point")))

    @with_wiki
    @patch('forgeimporters.trac.wiki.TracWikiImporter')
    def test_create(self, importer):
        from allura import model as M
        importer = importer.return_value
        importer.import_tool.return_value = Mock()
        importer.import_tool.return_value.url.return_value = '/p/test/mymount'
        params = dict(trac_url='http://example.com/trac/url',
                mount_label='mylabel',
                mount_point='mymount',
                )
        r = self.app.post('/p/test/admin/wiki/_importer/create', params,
                status=302)
        project = M.Project.query.get(shortname='test')
        self.assertEqual(r.location, 'http://localhost/p/test/mymount')
        self.assertEqual(project._id, importer.import_tool.call_args[0][0]._id)
        self.assertEqual(u'mymount', importer.import_tool.call_args[1]['mount_point'])
        self.assertEqual(u'mylabel', importer.import_tool.call_args[1]['mount_label'])
        self.assertEqual(u'http://example.com/trac/url', importer.import_tool.call_args[1]['trac_url'])
