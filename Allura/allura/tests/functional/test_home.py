import json
from pylons import g
from formencode.variabledecode import variable_encode

from ming.orm.ormsession import ThreadLocalORMSession

from allura.tests import TestController
from allura import model as M


class TestProjectHome(TestController):

    def test_project_nav(self):
        response = self.app.get('/p/test/_nav.json')
        root = self.app.get('/p/test/home/')
        nav_links = root.html.find('div', dict(id='top_nav')).findAll('a')
        assert len(nav_links) ==  len(response.json['menu'])
        for nl, entry in zip(nav_links, response.json['menu']):
            assert nl['href'] == entry['url']

    def test_home(self):
        r0 = self.app.get('/home/').body
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
        r1 = self.app.get('/home/').body
        assert r0 != r1

    def test_neighborhood_home(self):
        r0 = self.app.get('/p/test/home/').body
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
        r1 = self.app.get('/home/').body
        assert r0 != r1

    def test_user_subproject_home_not_profile(self):
        u_proj = M.Project.query.get(shortname='u/test-admin')
        u_proj.new_subproject('sub1')
        from ming.orm.ormsession import ThreadLocalORMSession
        ThreadLocalORMSession.flush_all()

        r = self.app.get('/u/test-admin/sub1/')
        assert r.location.endswith('home/'), r.location
        r.follow()

    def test_user_search(self):
        r = self.app.get('/p/test/user_search?term=test', status=200)
        j = json.loads(r.body)
        assert j['users'][0]['id'].startswith('test')

    def test_user_search_noparam(self):
        r = self.app.get('/p/test/user_search', status=400)

    def test_user_search_shortparam(self):
        r = self.app.get('/p/test/user_search?term=ad', status=400)
