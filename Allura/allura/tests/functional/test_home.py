#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import json
import re

from pylons import tmpl_context as c

from allura.tests import TestController
from allura.tests import decorators as td
from allura import model as M
from ming.orm import ThreadLocalORMSession

from nose.tools import assert_equal, assert_not_in


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
    def test_project_group_nav(self):
        c.user = M.User.by_username('test-admin')
        p = M.Project.query.get(shortname='test')
        c.project = p
        if 'wiki2' and not p.app_instance('wiki2'):
            c.app = p.install_app('wiki', 'wiki2', 'wiki2', 9)

        response = self.app.get('/p/test/_nav.json')
        menu = response.json['menu']
        wikis = menu[-2]['children']
        assert_equal(len(wikis), 2)
        assert {u'url': u'/p/test/wiki/', u'name': u'Wiki', u'icon': u'tool-wiki', 'tool_name': 'wiki'} in wikis, wikis
        assert {u'url': u'/p/test/wiki2/', u'name': u'wiki2', u'icon': u'tool-wiki', 'tool_name': 'wiki'} in wikis, wikis

    @td.with_wiki
    def test_project_group_nav_more_than_ten(self):
        for i in range(1,15):
            tool_name = "wiki%s" % str(i)
            c.user = M.User.by_username('test-admin')
            p = M.Project.query.get(shortname='test')
            c.project = p
            if tool_name and not p.app_instance(tool_name):
                c.app = p.install_app('wiki', tool_name, tool_name, i)
        response = self.app.get('/p/test/_nav.json')
        menu = response.json['menu']
        assert_equal(len(menu[0]['children']), 11)
        assert {u'url': u'/p/test/_list/wiki', u'name': u'More...', u'icon': u'tool-wiki', 'tool_name': 'wiki'} in menu[0]['children']

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
        assert_not_in('Profile', r.follow().body)

    def test_user_search(self):
        r = self.app.get('/p/test/user_search?term=test', status=200)
        j = json.loads(r.body)
        assert j['users'][0]['id'].startswith('test')

    def test_user_search_for_disabled_user(self):
        user = M.User.by_username('test-admin')
        user.disabled = True
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/p/test/user_search?term=test', status=200)
        j = json.loads(r.body)
        assert j == {'users': []}

    def test_user_search_noparam(self):
        r = self.app.get('/p/test/user_search', status=400)

    def test_user_search_shortparam(self):
        r = self.app.get('/p/test/user_search?term=ad', status=400)

    def test_users(self):
        r = self.app.get('/p/test/users', status=200)
        j = json.loads(r.body)
        expected = [{
            'value': u'test-admin',
            'label': u'Test Admin (test-admin)'
        }]
        assert_equal(j['options'], expected)

    def test_members(self):
        nbhd = M.Neighborhood.query.get(name='Projects')
        self.app.post('/admin/groups/create', params={'name': 'B_role'})
        test_project = M.Project.query.get(shortname='test', neighborhood_id=nbhd._id)
        test_project.add_user(M.User.by_username('test-user-1'), ['B_role'])
        test_project.add_user(M.User.by_username('test-user'), ['Developer'])
        test_project.add_user(M.User.by_username('test-user-0'), ['Member'])
        test_project.add_user(M.User.by_username('test-user-2'), ['Member'])
        test_project.add_user(M.User.by_username('test-user-3'), ['Member'])
        test_project.add_user(M.User.by_username('test-user-3'), ['Developer'])
        test_project.add_user(M.User.by_username('test-user-4'), ['Admin'])
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/p/test/_members/')

        assert '<td>Test Admin</td>' in r
        assert '<td><a href="/u/test-admin/">test-admin</a></td>' in r
        assert '<td>Admin</td>' in r
        tr = r.html.findAll('tr')
        assert "<td>Test Admin</td>" in str(tr[1])
        assert "<td>Test User 4</td>" in str(tr[2])
        assert "<td>Test User</td>" in str(tr[3])
        assert "<td>Test User 3</td>" in str(tr[4])
        assert "<td>Test User 0</td>" in str(tr[5])
        assert "<td>Test User 1</td>" in str(tr[6])
        assert "<td>Test User 2</td>" in str(tr[7])


    def test_members_anonymous(self):
        r = self.app.get('/p/test/_members/', extra_environ=dict(username='*anonymous'))
        assert '<td>Test Admin</td>' in r
        assert '<td><a href="/u/test-admin/">test-admin</a></td>' in r
        assert '<td>Admin</td>' in r
