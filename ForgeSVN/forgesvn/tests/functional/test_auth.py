# -*- coding: utf-8 -*-
import json
from datadiff.tools import assert_equal

from allura.tests import TestController
from forgesvn.tests import with_svn

class TestSVNAuth(TestController):

    @with_svn
    def test_refresh_repo(self):
        r = self.app.get('/auth/refresh_repo')
        assert_equal(r.body, 'No repo specified')

        r = self.app.get('/auth/refresh_repo/p/gbalksdfh')
        assert_equal(r.body, 'No project at /p/gbalksdfh')

        r = self.app.get('/auth/refresh_repo/p/test')
        assert_equal(r.body, '/p/test does not include a repo mount point')

        r = self.app.get('/auth/refresh_repo/p/test/blah/')
        assert_equal(r.body, 'Cannot find repo at /p/test/blah')

        r = self.app.get('/auth/refresh_repo/p/test/src/')
        assert_equal(r.body, '<Repository /tmp/svn/p/test/src> refresh queued.\n')

class TestSVNUserPermissions(TestController):
    allow = dict(allow_read=True, allow_write=True, allow_create=True)
    read = dict(allow_read=True, allow_write=False, allow_create=False)
    disallow = dict(allow_read=False, allow_write=False, allow_create=False)

    @with_svn
    def test_list_repos(self):
        r = self.app.get('/auth/repo_permissions', params=dict(username='test-admin'), status=200)
        assert_equal(json.loads(r.body), {"allow_write": [
            '/svn/test/src',
        ]})
