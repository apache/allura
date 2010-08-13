import os

import pkg_resources
from pylons import c
from ming.orm import ThreadLocalORMSession

from allura.lib import helpers as h
from forgesvn.tests import TestController

class TestRootController(TestController):

    def setUp(self):
        TestController.setUp(self)
        h.set_context('test', 'src')
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testsvn'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_index(self):
        resp = self.app.get('/src/').follow()
        assert 'svn checkout' in resp
        assert 'Revision 3' in resp

    def test_commit(self):
        resp = self.app.get('/src/3/')
        assert len(resp.html.findAll('tr')) > 3, resp.showbrowser()

    def test_tree(self):
        resp = self.app.get('/src/1/tree/')
        assert len(resp.html.findAll('tr')) == 2, resp.showbrowser()
        resp = self.app.get('/src/1/tree/trunk/')
        assert len(resp.html.findAll('tr')) >= 2, resp.showbrowser()

    def test_file(self):
        resp = self.app.get('/src/1/tree/trunk/debug.py')
        assert 'postmortem debugging' in resp, resp.showbrowser()

    def test_diff(self):
        resp = self.app.get('/src/3/tree/trunk/clutch/command.py?diff=1')
        assert 'configure_logging' in resp, resp.showbrowser()
        assert '+++' in resp, resp.showbrowser()



