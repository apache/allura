import os

import pkg_resources
from pylons import c
from ming.orm import ThreadLocalORMSession

from pyforge.lib import helpers as h
from forgehg.tests import TestController

class TestRootController(TestController):

    def setUp(self):
        TestController.setUp(self)
        h.set_context('test', 'src_hg')
        repo_dir = pkg_resources.resource_filename(
            'forgehg', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testrepo.hg'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_index(self):
        resp = self.app.get('/src_hg/')
        assert 'hg clone http://' in resp, resp
        assert 'ready' in resp

    def test_commit(self):
        resp = self.app.get('/src_hg/tip/')
        assert '<ins>' in resp



