import json
import re

from allura.tests import TestController
from allura.tests import decorators as td
from allura import model as M


class TestProjectHome(TestController):

    @td.with_wiki
    def test_project_nav(self):
        response = self.app.get('/p/test/_nav.json')
        root = self.app.get('/p/test/wiki/').follow()
        assert re.search(r'<!-- Server: \S+ -->', str(root.html)), 'Missing Server comment'
        nav_links = root.html.find('div', dict(id='top_nav')).findAll('a')
        assert len(nav_links) ==  len(response.json['menu'])
        for nl, entry in zip(nav_links, response.json['menu']):
            assert nl['href'] == entry['url']

    @td.with_wiki
    def test_neighborhood_home(self):
        self.app.get('/p/test/wiki/', status=302)
        self.app.get('/adobe/test/wiki/', status=404)
        self.app.get('/adobe/no_such_project/wiki/', status=404)

    @td.with_user_project('test-admin')
    def test_user_subproject_home_not_profile(self):
        u_proj = M.Project.query.get(shortname='u/test-admin')
        u_proj.new_subproject('sub1')
        from ming.orm.ormsession import ThreadLocalORMSession
        ThreadLocalORMSession.flush_all()

        r = self.app.get('/u/test-admin/sub1/')
        assert r.location.endswith('admin/'), r.location
        r.follow()

    def test_user_search(self):
        r = self.app.get('/p/test/user_search?term=test', status=200)
        j = json.loads(r.body)
        assert j['users'][0]['id'].startswith('test')

    def test_user_search_noparam(self):
        r = self.app.get('/p/test/user_search', status=400)

    def test_user_search_shortparam(self):
        r = self.app.get('/p/test/user_search?term=ad', status=400)
