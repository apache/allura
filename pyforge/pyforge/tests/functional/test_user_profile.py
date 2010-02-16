from pylons import g
from formencode.variabledecode import variable_encode

from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.tests import TestController
from pyforge import model as M

class TestUserProfile(TestController):

    def test_profile(self):
        r0 = str(self.app.get('/profile/'))
        r = self.app.get('/profile/configuration')
        selects = r.html.findAll('select')
        options = selects[-1].findAll('option')
        wnames = [
            o['value'] for o in options ]
        params = variable_encode(dict(
                divs=[
                    dict(name='content',
                         content=[ dict(widget=wn) for wn in wnames ])
                    ]))
        self.app.post('/profile/update_configuration', params=params)
        r1 = str(self.app.get('/profile/'))
        assert r0 != r1

    def test_neighborhood_profile(self):
        r0 = str(self.app.get('/users/test_admin/profile/'))
        r2 = self.app.get('/users/no_such_user/profile/', status=404)
        r = self.app.get('/users/test_admin/profile/configuration')
        selects = r.html.findAll('select')
        options = selects[-1].findAll('option')
        wnames = [
            o['value'] for o in options ]
        params = variable_encode(dict(
                divs=[
                    dict(name='content',
                         content=[ dict(widget=wn) for wn in wnames ])
                    ]))
        self.app.post('/users/test_admin/profile/update_configuration', params=params)
        r1 = str(self.app.get('/profile/'))
        assert r0 != r1

    def test_seclusion(self):
        response = self.app.get('/users/test_admin/profile/')
        assert 'Email Addresses' in response
        response = self.app.get('/users/test_user/profile/')
        assert 'Email Addresses' not in response
