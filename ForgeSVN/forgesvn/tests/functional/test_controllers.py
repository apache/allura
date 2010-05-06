import os

import pkg_resources
from pylons import c
from ming.orm import ThreadLocalORMSession

from pyforge.lib import helpers as h
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
        resp = self.app.get('/src/')
        assert 'svn checkout' in resp
        assert 'ready' in resp
        assert 'Revision 1' in resp

    def test_commit(self):
        resp = self.app.get('/src/1/')
        assert '+' in resp



