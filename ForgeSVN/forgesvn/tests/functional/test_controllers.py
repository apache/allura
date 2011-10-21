import os

import pkg_resources
import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pylons import c
from ming.orm import ThreadLocalORMSession

from allura.lib import helpers as h
from alluratest.controller import TestController


class TestRootController(TestController):

    def setUp(self):
        TestController.setUp(self)
        h.set_context('test', 'src')
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data/')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testsvn'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        h.set_context('test', 'src')
        c.app.repo.refresh()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        h.set_context('test', 'src')

    def test_index(self):
        resp = self.app.get('/src/').follow()
        assert 'svn checkout' in resp
        assert '[r4]' in resp, resp.showbrowser()

    def test_index_empty(self):
        self.app.get('/svn/')

    def test_commit_browser(self):
        resp = self.app.get('/src/commit_browser')
        commit_script = resp.html.findAll('script')[1].contents[0]
        assert "var max_row = 5;" in commit_script
        assert "var next_column = 1;" in commit_script
        assert '{"column": 0, "series": 0, "url": "/p/test/src/1/", "parents": [], "message": "Create readme", "row": 4}' in commit_script

    def test_feed(self):
        r = self.app.get('/src/feed.rss')
        assert 'Remove hello.txt' in str(r), r

    def test_commit(self):
        resp = self.app.get('/src/3/tree/')
        assert len(resp.html.findAll('tr')) == 3, resp.showbrowser()

    def test_tree(self):
        resp = self.app.get('/src/1/tree/')
        assert len(resp.html.findAll('tr')) == 2, resp.showbrowser()
        resp = self.app.get('/src/3/tree/a/')
        assert len(resp.html.findAll('tr')) == 2, resp.showbrowser()

    def test_file(self):
        resp = self.app.get('/src/1/tree/README')
        assert 'README' in resp.html.find('h2',{'class':'dark title'}).contents[2]
        content = str(resp.html.find('div',{'class':'clip grid-19'}))
        assert 'This is readme' in content, content

    def test_invalid_file(self):
        resp = self.app.get('/src/1/tree/READMEz', status=404)

    def test_diff(self):
        resp = self.app.get('/src/3/tree/README?diff=2')
        assert 'This is readme' in resp, resp.showbrowser()
        assert '+++' in resp, resp.showbrowser()



