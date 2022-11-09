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
import os

from tg import tmpl_context as c
from ming.orm import ThreadLocalORMSession

import allura
from allura.tests import TestController
from allura.tests import decorators as td
from allura import model as M


class TestProjectHome(TestController):

    @td.with_wiki
    def test_project_nav(self):
        response = self.app.get('/p/test/_nav.json')
        root = self.app.get('/p/test/wiki/').follow()
        assert re.search(r'<!-- Server: \S+ -->',
                         str(root.html)), 'Missing Server comment'
        nav_links = root.html.find('div', dict(id='top_nav')).findAll('a')
        nav_links = [nl for nl in nav_links if 'add-tool-toggle' not in nl['class']]
        assert len(nav_links) == len(response.json['menu'])
        for nl, entry in zip(nav_links, response.json['menu']):
            assert nl['href'] == entry['url']

    @td.with_wiki
    def test_project_nav_with_admin_options(self):
        r = self.app.get('/p/test/_nav.json?admin_options=1')
        assert {
            "text": "Wiki",
            "href": "/p/test/admin/install_tool?tool_name=wiki",
            "tooltip":
                "Documentation is key to your project and the wiki tool helps make it easy for anyone to contribute."
        } in r.json['installable_tools']
        for m in r.json['menu']:
            if m['mount_point'] == 'sub1':
                assert (m['admin_options'] ==
                        [{'className': None,
                          'text': 'Subproject Admin',
                          'href': '/p/test/sub1/admin',
                          }])
                break
        else:
            raise AssertionError('Did not find sub1 subproject in menu results: {}'.format(r.json['menu']))
        for m in r.json['menu']:
            if m['mount_point'] == 'wiki':
                assert {'className': 'admin_modal',
                        'text': 'Set Home',
                        'href': '/p/test/admin/wiki/home',
                        } in m['admin_options']
                assert {'className': None,
                        'text': 'Permissions',
                        'href': '/p/test/admin/wiki/permissions',
                        } in m['admin_options']
                assert {'className': 'admin_modal',
                        'text': 'Delete Everything',
                        'href': '/p/test/admin/wiki/delete',
                        } in m['admin_options']
                break
        else:
            raise AssertionError('Did not find wiki in menu results: {}'.format(r.json['menu']))

    @td.with_wiki
    def test_project_group_nav(self):
        c.user = M.User.by_username('test-admin')
        p = M.Project.query.get(shortname='test')
        c.project = p
        if 'wiki2' and not p.app_instance('wiki2'):
            c.app = p.install_app('wiki', 'wiki2', 'wiki2', 9)

        response = self.app.get('/p/test/_nav.json')
        menu = response.json['menu']
        wiki_group = menu[-2]
        wikis = wiki_group.pop('children')
        assert {'url': '/p/test/_list/wiki', 'name': 'Wiki \u25be', 'mount_point': None,
                'icon': 'tool-wiki', 'tool_name': 'wiki', 'is_anchored': False} == wiki_group
        assert len(wikis) == 2
        assert {'url': '/p/test/wiki/', 'name': 'Wiki', 'mount_point': 'wiki',
                'icon': 'tool-wiki', 'tool_name': 'wiki', 'is_anchored': False} in wikis
        assert {'url': '/p/test/wiki2/', 'name': 'wiki2', 'mount_point': 'wiki2',
                'icon': 'tool-wiki', 'tool_name': 'wiki', 'is_anchored': False} in wikis

    def test_sitemap_limit_per_tool(self):
        """Test that sitemap is limited to max of 10 items per tool type."""
        c.user = M.User.by_username('test-admin')
        p = M.Project.query.get(shortname='test')
        c.project = p
        for i in range(11):
            mnt = 'wiki' + str(i)
            p.install_app('wiki', mnt, mnt, 10 + i)

        response = self.app.get('/p/test/_nav.json')
        menu = response.json['menu']
        wikis = menu[-2]['children']
        assert len(wikis) == 10

    @td.with_wiki
    def test_project_group_nav_more_than_ten(self):
        for i in range(1, 15):
            tool_name = "wiki%s" % str(i)
            c.user = M.User.by_username('test-admin')
            p = M.Project.query.get(shortname='test')
            c.project = p
            if tool_name and not p.app_instance(tool_name):
                c.app = p.install_app('wiki', tool_name, tool_name, i)
        response = self.app.get('/p/test/_nav.json')
        menu = response.json['menu']
        wiki_menu = [m for m in menu if m['tool_name'] == 'wiki'][0]
        assert len(wiki_menu['children']) == 10
        assert {'url': '/p/test/_list/wiki', 'name': 'More...', 'mount_point': None,
                'icon': 'tool-wiki', 'tool_name': 'wiki', 'is_anchored': False} in wiki_menu['children']

    @td.with_wiki
    def test_neighborhood_home(self):
        self.app.get('/p/test/wiki/', status=301)
        self.app.get('/adobe/test/wiki/', status=404)
        self.app.get('/adobe/no_such_project/wiki/', status=404)

    @td.with_user_project('test-admin')
    def test_user_subproject_home_not_profile(self):
        u_proj = M.Project.query.get(shortname='u/test-admin')
        u_proj.new_subproject('sub1')
        ThreadLocalORMSession.flush_all()

        r = self.app.get('/u/test-admin/sub1/')
        assert r.location.endswith('admin/'), r.location
        assert 'Profile' not in r.follow().text

    def test_user_icon_missing(self):
        r = self.app.get('/u/test-user/user_icon', status=302)
        assert r.location.endswith('images/user.png')

    def test_user_icon(self):
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(allura.__path__[0], 'nf', 'allura', 'images', file_name)
        file_data = open(file_path, 'rb').read()
        upload = ('icon', file_name, file_data)
        with td.audits('update project icon'):
            self.app.post('/u/test-admin/admin/update', params=dict(
                name='Test Project',
                shortname='test',
                short_description='A Test Project'),
                upload_files=[upload])
        r = self.app.get('/u/test-admin/user_icon')
        assert r.content_type == 'image/png'

    def test_user_search(self):
        r = self.app.get('/p/test/user_search?term=test', status=200)
        j = json.loads(r.text)
        assert j['users'][0]['id'].startswith('test')

    def test_user_search_for_disabled_user(self):
        user = M.User.by_username('test-admin')
        user.disabled = True
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/p/test/user_search?term=test', status=200)
        j = json.loads(r.text)
        assert j == {'users': []}

    def test_user_search_noparam(self):
        self.app.get('/p/test/user_search', status=400)

    def test_user_search_shortparam(self):
        self.app.get('/p/test/user_search?term=ad', status=400)

    def test_users(self):
        r = self.app.get('/p/test/users', status=200)
        j = json.loads(r.text)
        expected = [{
            'value': 'test-admin',
            'label': 'Test Admin (test-admin)'
        }]
        assert j['options'] == expected

    def test_members(self):
        nbhd = M.Neighborhood.query.get(name='Projects')
        self.app.post('/admin/groups/create', params={'name': 'B_role'})
        test_project = M.Project.query.get(
            shortname='test', neighborhood_id=nbhd._id)
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
        assert '<td><a href="/u/test-admin/profile/">test-admin</a></td>' in r
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
        r = self.app.get('/p/test/_members/',
                         extra_environ=dict(username='*anonymous'))
        assert '<td>Test Admin</td>' in r
        assert '<td><a href="/u/test-admin/profile/">test-admin</a></td>' in r
        assert '<td>Admin</td>' in r

    def test_toolaccess_before_subproject(self):
        self.app.extra_environ = {'username': 'test-admin'}
        # Add the subproject with a wiki.
        self.app.post('/p/test/admin/update_mounts', params={
            'new.install': 'install',
            'new.ep_name': '',
            'new.ordinal': '1',
            'new.mount_point': 'test-mount',
            'new.mount_label': 'Test Mount'})
        r = self.app.get('/p/test/test-mount/')
        assert r.location.endswith('admin/'), r.location

        pr = M.Project.query.get(shortname='test/test-mount')
        assert pr is not None
        c.user = M.User.query.get(username='test-admin')

        # Install and Verify a Tool in the subproject.
        pr.install_app(ep_name='Wiki', mount_point='test-sub', mount_label='Test Sub', ordinal='1')
        r = self.app.get('/p/test/test-mount/test-sub/').follow()
        active_link = r.html.findAll('li', {'class': 'selected'})
        assert len(active_link) == 1
        assert active_link[0].contents[1]['href'] == '/p/test/test-mount/test-sub/'
        assert 'Welcome to your wiki!' in r

        # Delete the Subproject.
        self.app.post('/p/test/admin/update_mounts', params={
            'subproject-0.delete': 'on',
            'subproject-0.shortname': 'test/test-mount',
            'new.ep_name': '',
        })

        # Try to access the  installed tool as anon.
        r = self.app.get('/p/test/test-mount/test-sub/', extra_environ=dict(username='*anonymous'), status=404)

        # Try to access the installed tool as Admin.
        r = self.app.get('/p/test/test-mount/test-sub/').follow()
        assert 'Wiki' in r

        # Install a new tool with same mount point in parent project. Here a Wiki is installed.
        p = M.Project.query.get(shortname='test')
        p.install_app(ep_name='Wiki', mount_point='test-mount', mount_label='Test Sub', ordinal='1')

        # Check if the tool is accessed and not the subproject.
        r = self.app.get('/p/test/test-mount/').follow()
        active_link = r.html.findAll('li', {'class': 'selected'})
        assert len(active_link) == 1
        assert active_link[0].contents[1]['href'] == '/p/test/test-mount/'
        assert 'Welcome to your wiki!' in r
