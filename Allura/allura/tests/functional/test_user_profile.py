from formencode.variabledecode import variable_encode

from allura.tests import decorators as td
from allura.tests import TestController

class TestUserProfile(TestController):

    @td.with_user_project('test-admin')
    def test_profile(self):
        response = self.app.get('/u/test-admin/profile/')
        assert '<h2 class="dark title">Test Admin' in response
        assert 'OpenIDs' in response

    def test_wrong_profile(self):
        response = self.app.get('/u/no-such-user/profile/', status=404)

    @td.with_user_project('test-admin')
    @td.with_user_project('test-user')
    def test_seclusion(self):
        response = self.app.get('/u/test-admin/profile/')
        assert 'Email Addresses' in response
        self.app.get('/u/test-user', extra_environ=dict(
                username='test-user'))
        response = self.app.get('/u/test-user/profile/')
        assert 'Email Addresses' not in response

    @td.with_user_project('test-admin')
    @td.with_wiki
    def test_feed(self):
        response = self.app.get('/u/test-admin/profile/feed')
        assert 'Recent posts by Test Admin' in response
        assert 'WikiPage Home modified by Test Admin' in response
