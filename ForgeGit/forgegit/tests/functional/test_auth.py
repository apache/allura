# -*- coding: utf-8 -*-
import json
from datadiff.tools import assert_equal

from allura.tests import TestController
from forgegit.tests import with_git

class TestGitUserPermissions(TestController):
    allow = dict(allow_read=True, allow_write=True, allow_create=True)
    read = dict(allow_read=True, allow_write=False, allow_create=False)
    disallow = dict(allow_read=False, allow_write=False, allow_create=False)

    def test_unknown_project(self):
        r = self._check_repo('/git/foo/bar', status=404)

    def test_unknown_app(self):
        r = self._check_repo('/git/test/bar')
        assert r == self.disallow, r

    @with_git
    def test_repo_write(self):
        r = self._check_repo('/git/test/src-git.git')
        assert r == self.allow, r
        r = self._check_repo('/git/test/src-git')
        assert r == self.allow, r

    @with_git
    def test_subdir(self):
        r = self._check_repo('/git/test/src-git.git/foo')
        assert r == self.allow, r
        r = self._check_repo('/git/test/src-git/foo')
        assert r == self.allow, r

    @with_git
    def test_neighborhood(self):
        r = self._check_repo('/git/test.p/src-git.git')
        assert r == self.allow, r

    @with_git
    def test_repo_read(self):
        r = self._check_repo(
            '/git/test.p/src-git.git',
            username='test-user')
        assert r == self.read, r

    def test_unknown_user(self):
        r = self._check_repo(
            '/git/test.p/src-git.git',
            username='test-usera',
            status=404)

    def _check_repo(self, path, username='test-admin', **kw):
        url = '/auth/repo_permissions'
        r = self.app.get(url, params=dict(
                repo_path=path,
                username=username), **kw)
        try:
            return r.json
        except:
            return r

    @with_git
    def test_list_repos(self):
        r = self.app.get('/auth/repo_permissions', params=dict(username='test-admin'), status=200)
        assert_equal(json.loads(r.body), {"allow_write": [
            '/git/test/src-git',
        ]})
