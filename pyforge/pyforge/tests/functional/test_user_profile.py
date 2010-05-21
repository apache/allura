from pylons import g
from formencode.variabledecode import variable_encode

from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.tests import TestController

class TestUserProfile(TestController):

    def test_profile(self):
        response = self.app.get('/u/test_admin/profile/')
        assert 'OpenIDs' in response
        response = self.app.get('/u/test_admin/profile/configuration')
        assert 'Configure Dashboard' in response

    def test_neighborhood_profile(self):
        response = self.app.get('/u/no_such_user/profile/', status=404)

    def test_seclusion(self):
        response = self.app.get('/u/test_admin/profile/')
        assert 'Email Addresses' in response
        response = self.app.get('/u/test_user/profile/')
        assert 'Email Addresses' not in response

class TestUserPermissions(TestController):
    allow = dict(allow_read=True, allow_write=True, allow_create=True)
    read = dict(allow_read=True, allow_write=False, allow_create=False)
    disallow = dict(allow_read=False, allow_write=False, allow_create=False)

    def test_unknown_project(self):
        r = self._check_repo('/git/foo/bar')
        assert r == self.disallow, r

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
            username='test_user')
        assert r == self.read, r

    def test_unknown_user(self):
        r = self._check_repo(
            '/git/test.p/src.git',
            username='test_usera',
            status=404)

    def _check_repo(self, path, username='test_admin', **kw):
        r = self.app.get(
            '/u/%s/profile/permissions' % username,
            params=dict(repo_path=path), **kw)
        try:
            return r.json
        except:
            return r

