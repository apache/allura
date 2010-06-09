from pylons import g
from formencode.variabledecode import variable_encode

from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.tests import TestController
from pyforge import model as M

class TestProjectHome(TestController):

    def test_project_nav(self):
        response = self.app.get('/p/test/_nav.json')
        root = self.app.get('/p/test/home/')
        nav_links = root.html.find('div', dict(id='nav_menu')).findAll('a')
        assert len(nav_links) ==  len(response.json['menu'])
        for nl, entry in zip(nav_links, response.json['menu']):
            assert nl['href'] == entry['url']

    def test_home(self):
        r0 = str(self.app.get('/home/'))
        r = self.app.get('/home/configuration')
        selects = r.html.findAll('select')
        options = selects[-1].findAll('option')
        wnames = [
            o['value'] for o in options ]
        params = variable_encode(dict(
                divs=[
                    dict(name='content',
                         content=[ dict(widget=wn) for wn in wnames ])
                    ]))
        self.app.post('/home/update_configuration', params=params)
        r1 = str(self.app.get('/home/'))
        assert r0 != r1

    def test_neighborhood_home(self):
        r0 = str(self.app.get('/p/test/home/'))
        r1 = self.app.get('/adobe/test/home/', status=302)
        r2 = self.app.get('/adobe/no_such_project/home/', status=404)
        r = self.app.get('/p/test/home/configuration')
        selects = r.html.findAll('select')
        options = selects[-1].findAll('option')
        wnames = [
            o['value'] for o in options ]
        params = variable_encode(dict(
                divs=[
                    dict(name='content',
                         content=[ dict(widget=wn) for wn in wnames ])
                    ]))
        self.app.post('/p/test/home/update_configuration', params=params)
        r1 = str(self.app.get('/home/'))
        assert r0 != r1

    def test_user_subproject_home_not_profile(self):
        r = self.app.get('/u/test-admin/sub1/')
        assert r.location.endswith('home/'), r.location
        r.follow()
