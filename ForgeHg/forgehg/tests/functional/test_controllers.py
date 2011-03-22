import os

import pkg_resources
from pylons import c
from ming.orm import ThreadLocalORMSession

from allura.lib import helpers as h
from alluratest.controller import TestController


class TestRootController(TestController):

    def setUp(self):
        TestController.setUp(self)
        h.set_context('test', 'src-hg')
        repo_dir = pkg_resources.resource_filename(
            'forgehg', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testrepo.hg'
        c.app.repo.refresh()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        h.set_context('test', 'src-hg')
        c.app.repo.refresh()

    def test_index(self):
        resp = self.app.get('/src-hg/').follow().follow()
        assert 'hg clone http://' in resp, resp

    def test_index_empty(self):
        self.app.get('/test-app-hg/')

    def test_commit_browser(self):
        resp = self.app.get('/src-hg/commit_browser')
        commit_script = resp.html.findAll('script')[1].contents[0]
        assert "var max_row = 5;" in commit_script
        assert "var next_column = 1;" in commit_script
        assert '{"column": 0, "series": 0, "url": "/p/test/src-hg/ci/0000000000000000000000000000000000000000/", "parents": [], "message": "", "row": 4}' in commit_script

    def _get_ci(self):
        resp = self.app.get('/src-hg/').follow().follow()
        for tag in resp.html.findAll('a'):
            if tag['href'].startswith('/p/test/src-hg/ci/'):
                return tag['href']
        return None

    def test_commit(self):
        ci = self._get_ci()
        resp = self.app.get(ci)
        assert 'Rick Copeland' in resp, resp.showbrowser()

    def test_tree(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/')
        assert len(resp.html.findAll('tr')) ==2, resp.showbrowser()
        assert 'README' in resp, resp.showbrowser()

    def test_file(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/README')
        assert 'README' in resp.html.find('h2',{'class':'dark title'}).contents[2]
        content = str(resp.html.find('div',{'class':'clip grid-19'}))
        assert 'This is readme' in content, content

    def test_invalid_file(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/READMEz', status=404)

    def test_diff(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/README')
        resp = resp.click(description='diff')
        assert 'readme' in resp, resp.showbrowser()
        assert '+++' in resp, resp.showbrowser()
