from formencode.variabledecode import variable_encode

from allura.tests import decorators as td
from allura.tests import TestController

class TestUserProfile(TestController):

    @td.with_user_project('test-admin')
    def test_profile(self):
        response = self.app.get('/u/test-admin/profile/')
        assert 'OpenIDs' in response
        response = self.app.get('/u/test-admin/profile/configuration')
        assert 'Configure Dashboard' in response

    @td.with_user_project('test-admin')
    def test_profile_config(self):
        # Not fully implemented, just do coverage
        response = self.app.post('/u/test-admin/profile/update_configuration', params=variable_encode({
                                     'layout_class': 'something', 'divs': [{'name': 'foo', 'content': [{'widget': 'lotsa/content'}]}],
                                     'new_div': {'name': 'bar', 'new_widget': 'widg'}}))

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
        assert '[test:wiki] test-admin created page Home' in response

