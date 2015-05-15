from datadiff.tools import assert_equal

from tg import config
from alluratest.controller import TestRestApiBase


class TestActivityHasAccessAPI(TestRestApiBase):

    def setUp(self, *args, **kwargs):
        super(TestActivityHasAccessAPI, self).setUp(*args, **kwargs)
        self._enabled = config.get('activitystream.enabled', 'false')
        config['activitystream.enabled'] = 'true'

    def tearDown(self, *args, **kwargs):
        super(TestActivityHasAccessAPI, self).tearDown(*args, **kwargs)
        config['activitystream.enabled'] = self._enabled

    def test_has_access_no_params(self):
        r = self.api_get('/rest/p/test/activity/has_access', status=404)
        r = self.api_get('/rest/p/test/activity/has_access?user=root', status=404)
        r = self.api_get('/rest/p/test/activity/has_access?perm=read', status=404)

    def test_has_access_unknown_params(self):
        """Unknown user and/or permission always False for has_access API"""
        r = self.api_get(
            '/rest/p/test/activity/has_access?user=babadook&perm=read',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
        r = self.api_get(
            '/rest/p/test/activity/has_access?user=test-user&perm=jump',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)

    def test_has_access_not_admin(self):
        """
        User which has no 'admin' permission on neighborhood can't use
        has_access API
        """
        self.api_get(
            '/rest/p/test/activity/has_access?user=test-admin&perm=admin',
            user='test-user',
            status=403)

    def test_has_access(self):
        r = self.api_get(
            '/rest/p/test/activity/has_access?user=test-admin&perm=admin',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], True)
        r = self.api_get(
            '/rest/p/test/activity/has_access?user=test-user&perm=admin',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
