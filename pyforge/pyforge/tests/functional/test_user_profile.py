from pylons import g
from formencode.variabledecode import variable_encode

from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.tests import TestController
from pyforge import model as M

class TestUserProfile(TestController):

    def test_profile(self):
        response = self.app.get('/users/test_admin/profile/')
        assert 'OpenIDs' in response
        response = self.app.get('/users/test_admin/profile/configuration')
        assert 'Configure Dashboard' in response

    def test_neighborhood_profile(self):
        response = self.app.get('/users/no_such_user/profile/', status=404)

    def test_seclusion(self):
        response = self.app.get('/users/test_admin/profile/')
        assert 'Email Addresses' in response
        response = self.app.get('/users/test_user/profile/')
        assert 'Email Addresses' not in response
