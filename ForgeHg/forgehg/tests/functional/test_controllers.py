import os

import pkg_resources
from pylons import c
from ming.orm import ThreadLocalORMSession

from allura.lib import helpers as h
from forgehg.tests import TestController

class TestRootController(TestController):

    def setUp(self):
        TestController.setUp(self)
        h.set_context('test', 'src-hg')
        repo_dir = pkg_resources.resource_filename(
            'forgehg', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testrepo.hg'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_index(self):
        resp = self.app.get('/src-hg/').follow().follow()
        assert 'hg clone http://' in resp, resp

    def _get_ci(self):
        resp = self.app.get('/src-hg/').follow().follow()
        for tag in resp.html.findAll('a'):
            if tag['href'].startswith('/p/test/src-hg/ci/'):
                return tag['href']
        return None

    def test_commit(self):
        ci = self._get_ci()
        resp = self.app.get(ci)
        assert 'Jenny Steele' in resp, resp.showbrowser()

    def test_tree(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/')
        assert len(resp.html.findAll('tr')) ==7, resp.showbrowser()
        resp = self.app.get(ci + 'tree/ew/')
        assert 'resource.py' in resp, resp.showbrowser()

    def test_file(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/ew/resource.py')
        assert 'ResourceManager' in resp, resp.showbrowser()

    def test_diff(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/ew/resource.py')
        resp = resp.click(description='diff')
        assert 'ew.templates.csscript' in resp, resp.showbrowser()
        assert 'ew.templates.cssscript' in resp, resp.showbrowser()
        assert '+++' in resp, resp.showbrowser()
