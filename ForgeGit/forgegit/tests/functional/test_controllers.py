import os

import pkg_resources
from pylons import c
from ming.orm import ThreadLocalORMSession

from pyforge.lib import helpers as h
from forgegit.tests import TestController

class TestRootController(TestController):

    def setUp(self):
        TestController.setUp(self)
        h.set_context('test', 'src_git')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testgit.git'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_index(self):
        resp = self.app.get('/src_git/')
        assert 'git://' in resp
        assert 'ready' in resp

    def test_commit(self):
        self.app.get('/src_git/HEAD/')



