from pylons import g
from formencode.variabledecode import variable_encode

from ming.orm.ormsession import ThreadLocalORMSession

from allura.tests import TestController

class TestUserProfile(TestController):

    def test_profile(self):
        response = self.app.get('/u/test-admin/profile/')
        assert 'OpenIDs' in response
        response = self.app.get('/u/test-admin/profile/configuration')
        assert 'Configure Dashboard' in response

    def test_neighborhood_profile(self):
        response = self.app.get('/u/no-such-user/profile/', status=404)

    def test_seclusion(self):
        response = self.app.get('/u/test-admin/profile/')
        assert 'Email Addresses' in response
        self.app.get('/u/test-user', extra_environ=dict(
                username='test-user'))
        response = self.app.get('/u/test-user/profile/')
        assert 'Email Addresses' not in response

class TestUserPermissions(TestController):
    allow = dict(allow_read=True, allow_write=True, allow_create=True)
    read = dict(allow_read=True, allow_write=False, allow_create=False)
    disallow = dict(allow_read=False, allow_write=False, allow_create=False)

    def test_unknown_project(self):
        r = self._check_repo('/git/foo/bar', status=404)

    def test_unknown_app(self):
        r = self._check_repo('/git/test/bar')
        assert r == self.disallow, r

    def test_repo_write(self):
        r = self._check_repo('/git/test/src.git')
        assert r == self.allow, r
        r = self._check_repo('/git/test/src')
        assert r == self.allow, r

    def test_subdir(self):
        r = self._check_repo('/git/test/src.git/foo')
        assert r == self.allow, r
        r = self._check_repo('/git/test/src/foo')
        assert r == self.allow, r

    def test_neighborhood(self):
        r = self._check_repo('/git/test.p/src.git')
        assert r == self.allow, r

    def test_repo_read(self):
        r = self._check_repo(
            '/git/test.p/src.git',
            username='test-user')
        assert r == self.read, r

    def test_unknown_user(self):
        r = self._check_repo(
            '/git/test.p/src.git',
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

