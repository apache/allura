import json
from datadiff.tools import assert_equal

from allura.tests import TestController

from forgehg.tests import with_hg

class TestUserPermissions(TestController):
    allow = dict(allow_read=True, allow_write=True, allow_create=True)
    read = dict(allow_read=True, allow_write=False, allow_create=False)
    disallow = dict(allow_read=False, allow_write=False, allow_create=False)

    @with_hg
    def test_list_repos(self):
        r = self.app.get('/auth/repo_permissions', params=dict(username='test-admin'), status=200)
        assert_equal(json.loads(r.body), {"allow_write": [
            '/hg/test/src-hg',
        ]})
