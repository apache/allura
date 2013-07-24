from unittest import TestCase
from mock import Mock, patch

from allura.tests import TestController
from allura.tests.decorators import with_tool


# important to be distinct from 'test' which ForgeSVN uses, so that the tests can run in parallel and not clobber each other
test_project_with_repo = 'test2'
with_svn = with_tool(test_project_with_repo, 'SVN', 'src', 'SVN')


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

    @patch('forgeimporters.google.code.GoogleCodeProjectExtractor.get_repo_type')
    @patch('forgeimporters.google.code.get_repo_url')
    def test_import_tool_happy_path(self, get_repo_url, get_repo_type):
        get_repo_type.return_value = 'git'
        get_repo_url.return_value = 'http://remote/clone/url/'
        p = self._make_project(gc_proj_name='myproject')
        GoogleRepoImporter().import_tool(p)
        p.install_app.assert_called_once_with('Git',
                mount_point='code',
                mount_label='Code',
                init_from_url='http://remote/clone/url/',
                )

    def test_no_project(self):
        with self.assertRaises(Exception) as cm:
            GoogleRepoImporter().import_tool()
        self.assertEqual(str(cm.exception), "You must supply a project")

    def test_no_google_code_project_name(self):
        p = self._make_project()
        with self.assertRaises(Exception) as cm:
            GoogleRepoImporter().import_tool(p)
        self.assertEqual(str(cm.exception), "Missing Google Code project name")


class TestGoogleRepoImportController(TestController, TestCase):
    def setUp(self):
        """Mount Google Code importer on the SVN admin controller"""
        super(TestGoogleRepoImportController, self).setUp()
        from forgesvn.svn_main import SVNRepoAdminController
        SVNRepoAdminController._importer = GoogleRepoImportController()

    @with_svn
    def test_index(self):
        r = self.app.get('/p/{}/admin/src/_importer/'.format(test_project_with_repo))
        self.assertIsNotNone(r.html.find(attrs=dict(name="gc_project_name")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_label")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_point")))

    @with_svn
    @patch('forgeimporters.google.code.GoogleRepoImporter')
    def test_create(self, gri):
        from allura import model as M
        gri.import_tool.return_value = Mock()
        gri.import_tool.return_value.url.return_value = '/p/{}/mymount'.format(test_project_with_repo)
        params = dict(gc_project_name='poop',
                mount_label='mylabel',
                mount_point='mymount',
                )
        r = self.app.post('/p/{}/admin/src/_importer/create'.format(test_project_with_repo),
                params,
                status=302)
        project = M.Project.query.get(shortname=test_project_with_repo)
        self.assertEqual(r.location, 'http://localhost/p/{}/mymount'.format(test_project_with_repo))
        self.assertEqual(project.get_tool_data('google-code', 'project_name'),
                'poop')
        self.assertEqual(project._id, gri.import_tool.call_args[0][0]._id)
        self.assertEqual(u'mymount', gri.import_tool.call_args[1]['mount_point'])
        self.assertEqual(u'mylabel', gri.import_tool.call_args[1]['mount_label'])
