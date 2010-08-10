import os

import pkg_resources
from pylons import c
from ming.orm import ThreadLocalORMSession

from pyforge.lib import helpers as h
from forgegit.tests import TestController

class TestRootController(TestController):

    def setUp(self):
        TestController.setUp(self)
        h.set_context('test', 'src-git')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testgit.git'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_index(self):
        resp = self.app.get('/src-git/').follow().follow()
        assert 'git://' in resp

    def _get_ci(self):
        resp = self.app.get('/src-git/ref/master:/').follow()
        for tag in resp.html.findAll('a'):
            if tag['href'].startswith('/p/test/src-git/ci/'):
                return tag['href']
        return None

    def test_commit(self):
        ci = self._get_ci()
        resp = self.app.get(ci)
        assert 'Sebastian' in resp, resp.showbrowser()

    def test_tree(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/')
        assert len(resp.html.findAll('tr')) > 6, resp.showbrowser()
        resp = self.app.get(ci + 'tree/doc/')
        assert 'roadmap.rst' in resp, resp.showbrowser()

    def test_file(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/doc/index.rst')
        assert 'GitPython' in resp, resp.showbrowser()

    def test_diff(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/doc/index.rst?diff=501bf602abea7d21c3dbb409b435976e92033145')
        assert 'GitPython Documentation' in resp, resp.showbrowser()
        assert '+++' in resp, resp.showbrowser()


