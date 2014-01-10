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
from mock import Mock, patch, MagicMock
from ming.odm import ThreadLocalORMSession

from allura.tests import TestController
from allura.tests.decorators import with_tool
from allura import model as M


# important to be distinct from 'test' which ForgeSVN uses, so that the
# tests can run in parallel and not clobber each other
test_project_with_repo = 'test2'


from forgeimporters.google.code import (
    get_repo_url,
    GoogleRepoImporter,
    GoogleRepoImportController,
)


class TestGetRepoUrl(TestCase):

    def test_svn(self):
        r = get_repo_url('projname', 'svn')
        self.assertEqual(r, 'http://projname.googlecode.com/svn/')

    def test_git(self):
        r = get_repo_url('projname', 'git')
        self.assertEqual(r, 'https://code.google.com/p/projname/')

    def test_hg(self):
        r = get_repo_url('projname', 'hg')
        self.assertEqual(r, 'https://code.google.com/p/projname/')


class TestGoogleRepoImporter(TestCase):

    def _make_project(self, gc_proj_name=None):
        project = Mock()
        project.get_tool_data.side_effect = lambda *args: gc_proj_name
        return project

    @patch('forgeimporters.google.code.g')
    @patch('forgeimporters.google.code.M')
    @patch('forgeimporters.google.code.GoogleCodeProjectExtractor')
    @patch('forgeimporters.google.code.get_repo_url')
    def test_import_tool_happy_path(self, get_repo_url, gcpe, M, g):
        gcpe.return_value.get_repo_type.return_value = 'git'
        get_repo_url.return_value = 'http://remote/clone/url/'
        p = self._make_project(gc_proj_name='myproject')
        u = Mock(name='c.user')
        app = p.install_app.return_value
        app.config.options.mount_point = 'code'
        app.url = 'foo'
        GoogleRepoImporter().import_tool(p, u, project_name='project_name')
        get_repo_url.assert_called_once_with('project_name', 'git')
        p.install_app.assert_called_once_with('Git',
                                              mount_point='code',
                                              mount_label='Code',
                                              init_from_url='http://remote/clone/url/',
                                              import_id={
                                                  'source': 'Google Code',
                                                  'project_name': 'project_name',
                                              },
                                              )
        M.AuditLog.log.assert_called_once_with(
            'import tool code from project_name on Google Code',
            project=p, user=u, url='foo')
        g.post_event.assert_called_once_with('project_updated')


class TestGoogleRepoImportController(TestController, TestCase):

    def test_index(self):
        r = self.app.get(
            '/p/{}/admin/ext/import/google-code-repo/'.format(test_project_with_repo))
        self.assertIsNotNone(r.html.find(attrs=dict(name="gc_project_name")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_label")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_point")))

    @patch('forgeimporters.google.code.GoogleCodeProjectExtractor')
    @patch('forgeimporters.base.import_tool')
    def test_create(self, import_tool, extractor):
        extractor.return_value.get_repo_type.return_value = 'git'
        params = dict(gc_project_name='poop',
                      mount_label='mylabel',
                      mount_point='mymount',
                      )
        r = self.app.post(
            '/p/{}/admin/ext/import/google-code-repo/create'.format(test_project_with_repo),
            params,
            status=302)
        self.assertEqual(
            r.location, 'http://localhost/p/{}/admin/'.format(test_project_with_repo))
        self.assertEqual(
            u'mymount', import_tool.post.call_args[1]['mount_point'])
        self.assertEqual(
            u'mylabel', import_tool.post.call_args[1]['mount_label'])
        self.assertEqual(
            u'poop', import_tool.post.call_args[1]['project_name'])

    @patch('forgeimporters.google.code.GoogleCodeProjectExtractor')
    @patch('forgeimporters.base.import_tool')
    def test_create_limit(self, import_tool, extractor):
        extractor.return_value.get_repo_type.return_value = 'git'
        project = M.Project.query.get(shortname=test_project_with_repo)
        project.set_tool_data('GoogleRepoImporter', pending=1)
        ThreadLocalORMSession.flush_all()
        params = dict(gc_project_name='poop',
                      mount_label='mylabel',
                      mount_point='mymount',
                      )
        r = self.app.post(
            '/p/{}/admin/ext/import/google-code-repo/create'.format(test_project_with_repo),
            params,
            status=302).follow()
        self.assertIn('Please wait and try again', r)
        self.assertEqual(import_tool.post.call_count, 0)
