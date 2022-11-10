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
import os
from io import BytesIO
import six.moves.urllib.parse
import six.moves.urllib.request
import six.moves.urllib.error

import PIL
from mock import patch
from tg import config
from ming.orm.ormsession import ThreadLocalORMSession, session
from paste.httpexceptions import HTTPFound, HTTPMovedPermanently
from tg import app_globals as g, tmpl_context as c

import allura
from allura import model as M
from allura.tests import TestController
from allura.tests import decorators as td
from allura.lib import helpers as h
from allura.lib import utils
from alluratest.controller import setup_trove_categories


class TestNeighborhood(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        self._cleanup_audit_log()

    def teardown_method(self, method):
        super().teardown_method(method)
        self._cleanup_audit_log()

    def _cleanup_audit_log(self):
        M.AuditLog.query.remove({})

    def test_home_project(self):
        r = self.app.get('/adobe/wiki/', status=301)
        assert r.location.endswith('/adobe/wiki/Home/')
        r = r.follow()
        assert 'This is the "Adobe" neighborhood' in str(r), str(r)
        r = self.app.get(
            '/adobe/admin/', extra_environ=dict(username='test-user'),
            status=403)

    def test_redirect(self):
        r = self.app.post('/adobe/_admin/update',
                          params=dict(redirect='wiki/Home/'),
                          extra_environ=dict(username='root'))
        r = self.app.get('/adobe/')
        assert r.location.endswith('/adobe/wiki/Home/')

    @patch('allura.model.neighborhood.Neighborhood.use_wiki_page_as_root', True)
    def test_wiki_as_home(self):
        r = self.app.get('/adobe/', status=200)
        assert 'This is the "Adobe" neighborhood' in str(r), str(r)

    def test_admin(self):
        r = self.app.get('/adobe/_admin/', extra_environ=dict(username='root'))
        r = self.app.get('/adobe/_admin/overview',
                         extra_environ=dict(username='root'))
        r = self.app.get('/adobe/_admin/accolades',
                         extra_environ=dict(username='root'))
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['google_analytics'] = True
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Mozq1', css='',
                                      homepage='# MozQ1!', tracking_id='U-123456'),
                          extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Mozq1', css='',
                                      homepage='# MozQ1!\n[Root]'),
                          extra_environ=dict(username='root'))
        # make sure project_template is validated as proper json
        r = self.app.post('/adobe/_admin/update',
                          params=dict(project_template='{'),
                          extra_environ=dict(username='root'))
        assert 'Invalid JSON' in r

    def test_admin_overview_audit_log(self):

        def check_log(message):
            return M.AuditLog.query.find({'message': message}).count() == 1

        nbhd = M.Neighborhood.query.get(name='Projects')
        nbhd.features['css'] = 'custom'
        nbhd.features['google_analytics'] = True
        params = {
            'name': 'Pjs',
            'redirect': 'http://fake.org/',
            'show_title': 'false',
            'allow_browse': 'false',
            'css': '.class { border: 1px; }',
            'homepage': '[Homepage]',
            'project_list_url': 'http://fake.org/project_list',
            'project_template': '{"name": "template"}',
            'tracking_id': 'U-123456',
            'prohibited_tools': 'wiki, tickets',
            'anchored_tools': 'wiki:Wiki',
        }

        self.app.post('/p/_admin/update', params=params,
                      extra_environ=dict(username='root'))

        assert check_log('change neighborhood name to Pjs')
        assert check_log('change neighborhood redirect to http://fake.org/')
        assert check_log('change neighborhood show title to False')
        assert check_log('change neighborhood allow browse to False')
        assert check_log('change neighborhood css to .class { border: 1px; }')
        assert check_log('change neighborhood homepage to [Homepage]')
        assert check_log('change neighborhood project list url to '
                         'http://fake.org/project_list')

        assert check_log('change neighborhood project template to '
                         '{"name": "template"}')
        assert check_log('update neighborhood tracking_id')
        assert check_log('update neighborhood prohibited tools')
        assert check_log('update neighborhood anchored tools')

        # must get as many log records as many values are updated
        assert M.AuditLog.query.find().count() == len(params)

    def test_prohibited_tools(self):
        self.app.post('/p/_admin/update',
                      params=dict(name='Projects',
                                  prohibited_tools='wiki, tickets'),
                      extra_environ=dict(username='root'))

        r = self.app.get('/p/_admin/overview', extra_environ=dict(username='root'))
        assert 'wiki, tickets' in r

        c.user = M.User.query.get(username='root')
        c.project = M.Project.query.get(shortname='test')
        data = c.project.nav_data(admin_options=True)

        assert 'Wiki' not in data
        assert 'Tickets' not in data

        r = self.app.post('/p/_admin/update',
                          params=dict(name='Projects',
                                      prohibited_tools='wiki, test'),
                          extra_environ=dict(username='root'))
        assert 'error' in self.webflash(r), self.webflash(r)

    @td.with_wiki
    def test_anchored_tools(self):
        neighborhood = M.Neighborhood.query.get(name='Projects')

        r = self.app.post('/p/_admin/update',
                          params=dict(name='Projects',
                                      anchored_tools='wiki:Wiki, tickets:Ticket'),
                          extra_environ=dict(username='root'))
        assert 'error' not in self.webflash(r)
        r = self.app.post('/p/_admin/update',
                          params=dict(name='Projects',
                                      anchored_tools='w!iki:Wiki, tickets:Ticket'),
                          extra_environ=dict(username='root'))
        assert 'error' in self.webflash(r)
        assert neighborhood.anchored_tools == 'wiki:Wiki, tickets:Ticket'

        r = self.app.post('/p/_admin/update',
                          params=dict(name='Projects',
                                      anchored_tools='wiki:Wiki,'),
                          extra_environ=dict(username='root'))
        assert 'error' in self.webflash(r)
        assert neighborhood.anchored_tools == 'wiki:Wiki, tickets:Ticket'

        r = self.app.post('/p/_admin/update',
                          params=dict(name='Projects',
                                      anchored_tools='badname,'),
                          extra_environ=dict(username='root'))
        assert 'error' in self.webflash(r)
        assert neighborhood.anchored_tools == 'wiki:Wiki, tickets:Ticket'

        r = self.app.get('/p/test/admin/overview')
        top_nav = r.html.find(id='top_nav')
        assert top_nav.find(href='/p/test/wiki/'), top_nav
        assert top_nav.find(href='/p/test/tickets/'), top_nav

        c.user = M.User.query.get(username='root')
        c.project = M.Project.query.get(shortname='test')
        data = c.project.nav_data(admin_options=True)
        for tool in data['menu']:
            if tool['name'].lower() == 'wiki':
                menu = [name['text'] for name in tool['admin_options']]
                assert 'Delete' not in menu
                break

    def test_show_title(self):
        r = self.app.get('/adobe/_admin/overview',
                         extra_environ=dict(username='root'))
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        # if not set show_title must be True
        assert neighborhood.show_title
        # title should be present
        assert 'class="project_title"' in str(r)
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Mozq1', css='',
                                      homepage='# MozQ1!',
                                      tracking_id='U-123456',
                                      show_title='false'),
                          extra_environ=dict(username='root'))
        # no title now
        r = self.app.get('/adobe/', extra_environ=dict(username='root'))
        assert 'class="project_title"' not in str(r)
        r = self.app.get('/adobe/wiki/Home/',
                         extra_environ=dict(username='root'))
        assert 'class="project_title"' not in str(r)

        # title must be present on project page
        r = self.app.get('/adobe/adobe-1/admin/',
                         extra_environ=dict(username='root'))
        assert 'class="project_title"' in str(r)

    def test_admin_stats_del_count(self):
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        proj = M.Project.query.get(neighborhood_id=neighborhood._id)
        proj.deleted = True
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/adobe/_admin/stats/',
                         extra_environ=dict(username='root'))
        assert 'Deleted: 1' in r
        assert 'Private: 0' in r

    def test_admin_stats_priv_count(self):
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        proj = M.Project.query.get(neighborhood_id=neighborhood._id)
        proj.deleted = False
        proj.private = True
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/adobe/_admin/stats/',
                         extra_environ=dict(username='root'))
        assert 'Deleted: 0' in r
        assert 'Private: 1' in r

    def test_admin_stats_adminlist(self):
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        proj = M.Project.query.get(neighborhood_id=neighborhood._id)
        proj.private = False
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/adobe/_admin/stats/adminlist',
                         extra_environ=dict(username='root'))
        pq = M.Project.query.find(
            dict(neighborhood_id=neighborhood._id, deleted=False))
        pq.sort('name')
        projects = pq.skip(0).limit(int(25)).all()
        for proj in projects:
            admin_role = M.ProjectRole.query.get(
                project_id=proj.root_project._id, name='Admin')
            if admin_role is None:
                continue
            user_role_list = M.ProjectRole.query.find(
                dict(project_id=proj.root_project._id, name=None)).all()
            for ur in user_role_list:
                if ur.user is not None and admin_role._id in ur.roles:
                    assert proj.name in r
                    assert ur.user.username in r

    def test_icon(self):
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(
            allura.__path__[0], 'nf', 'allura', 'images', file_name)
        file_data = open(file_path, 'rb').read()
        upload = ('icon', file_name, file_data)

        r = self.app.get('/adobe/_admin/', extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Mozq1', css='',
                                      homepage='# MozQ1'),
                          extra_environ=dict(username='root'), upload_files=[upload])
        r = self.app.get('/adobe/icon')
        image = PIL.Image.open(BytesIO(r.body))
        assert image.size == (48, 48)

        r = self.app.get('/adobe/icon?foo=bar')

    def test_google_analytics(self):
        # analytics allowed
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['google_analytics'] = True
        r = self.app.get('/adobe/_admin/overview',
                         extra_environ=dict(username='root'))
        assert 'Google Analytics ID' in r
        r = self.app.get('/adobe/adobe-1/admin/overview',
                         extra_environ=dict(username='root'))
        assert 'Google Analytics ID' in r
        r = self.app.post('/adobe/_admin/update',
                          params=dict(name='Adobe', css='',
                                      homepage='# MozQ1', tracking_id='U-123456'),
                          extra_environ=dict(username='root'), status=302)
        r = self.app.post('/adobe/adobe-1/admin/update',
                          params=dict(tracking_id='U-654321'),
                          extra_environ=dict(username='root'), status=302)
        r = self.app.get('/adobe/adobe-1/admin/overview',
                         extra_environ=dict(username='root'))
        assert "_add_tracking('nbhd', 'U-123456');" in r, r
        assert "_add_tracking('proj', 'U-654321');" in r
        # analytics not allowed
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['google_analytics'] = False
        r = self.app.get('/adobe/_admin/overview',
                         extra_environ=dict(username='root'))
        assert 'Google Analytics ID' not in r
        r = self.app.get('/adobe/adobe-1/admin/overview',
                         extra_environ=dict(username='root'))
        assert 'Google Analytics ID' not in r
        r = self.app.get('/adobe/adobe-1/admin/overview',
                         extra_environ=dict(username='root'))
        assert "_add_tracking('nbhd', 'U-123456');" not in r
        assert "_add_tracking('proj', 'U-654321');" not in r

    def test_custom_css(self):
        test_css = '.test{color:red;}'
        custom_css = 'Custom CSS'

        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.css = test_css
        neighborhood.features['css'] = 'none'
        r = self.app.get('/adobe/')
        assert test_css not in r
        r = self.app.get('/adobe/_admin/overview',
                         extra_environ=dict(username='root'))
        assert custom_css not in r

        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['css'] = 'picker'
        r = self.app.get('/adobe/')
        while isinstance(r.response, HTTPFound) or isinstance(r.response, HTTPMovedPermanently):
            r = r.follow()
        assert test_css in r
        r = self.app.get('/adobe/_admin/overview',
                         extra_environ=dict(username='root'))
        assert custom_css in r

        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['css'] = 'custom'
        r = self.app.get('/adobe/')
        while isinstance(r.response, HTTPFound) or isinstance(r.response, HTTPMovedPermanently):
            r = r.follow()
        assert test_css in r
        r = self.app.get('/adobe/_admin/overview',
                         extra_environ=dict(username='root'))
        assert custom_css in r

    def test_picker_css(self):
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.features['css'] = 'picker'

        r = self.app.get('/adobe/_admin/overview',
                         extra_environ=dict(username='root'))
        assert 'Project title, font' in r
        assert 'Project title, color' in r
        assert 'Bar on top' in r
        assert 'Title bar, background' in r
        assert 'Title bar, foreground' in r

        r = self.app.post('/adobe/_admin/update',
                          params={'name': 'Adobe',
                                  'css': '',
                                  'homepage': '',
                                  'css-projecttitlefont': 'arial,sans-serif',
                                  'css-projecttitlecolor': 'green',
                                  'css-barontop': '#555555',
                                  'css-titlebarbackground': '#333',
                                  'css-titlebarcolor': '#444'},
                          extra_environ=dict(username='root'), upload_files=[])
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        assert '/*projecttitlefont*/.project_title{font-family:arial,sans-serif;}' in neighborhood.css
        assert '/*projecttitlecolor*/.project_title{color:green;}' in neighborhood.css
        assert '/*barontop*/.pad h2.colored {background-color:#555555; background-image: none;}' in neighborhood.css
        assert '/*titlebarbackground*/.pad h2.title{background-color:#333; background-image: none;}' in neighborhood.css
        assert "/*titlebarcolor*/.pad h2.title, .pad h2.title small a {color:#444;}" in neighborhood.css

    def test_max_projects(self):
        # Set max value to unlimit
        neighborhood = M.Neighborhood.query.get(name='Projects')
        neighborhood.features['max_projects'] = None
        r = self.app.post('/p/register',
                          params=dict(
                              project_unixname='maxproject1', project_name='Max project1',
                              project_description='', neighborhood='Projects'),
                          antispam=True,
                          extra_environ=dict(username='root'), status=302)
        assert '/p/maxproject1/admin' in r.location

        # Set max value to 0
        neighborhood = M.Neighborhood.query.get(name='Projects')
        neighborhood.features['max_projects'] = 0
        r = self.app.post('/p/register',
                          params=dict(
                              project_unixname='maxproject2', project_name='Max project2',
                              project_description='', neighborhood='Projects'),
                          antispam=True,
                          extra_environ=dict(username='root'))
        while isinstance(r.response, HTTPFound):
            r = r.follow()
        assert 'You have exceeded the maximum number of projects' in r

    def test_project_rate_limit(self):
        # Set rate limit to unlimit
        with h.push_config(config, **{'project.rate_limits': '{}'}):
            r = self.app.post('/p/register',
                              params=dict(
                                  project_unixname='rateproject1', project_name='Rate project1',
                                  project_description='', neighborhood='Projects'),
                              antispam=True,
                              extra_environ=dict(username='test-user-1'), status=302)
            assert '/p/rateproject1/admin' in r.location

        # Set rate limit to 1 in first hour of user account
        with h.push_config(config, **{'project.rate_limits': '{"3600": 1}'}):
            r = self.app.post('/p/register',
                              params=dict(
                                  project_unixname='rateproject2', project_name='Rate project2',
                                  project_description='', neighborhood='Projects'),
                              antispam=True,
                              extra_environ=dict(username='test-user-1'))
            while isinstance(r.response, HTTPFound):
                r = r.follow()
            assert 'Project creation rate limit exceeded.  Please try again later.' in r

    def test_project_rate_limit_admin(self):
        # Set rate limit to unlimit
        with h.push_config(config, **{'project.rate_limits': '{}'}):
            r = self.app.post('/p/register',
                              params=dict(
                                  project_unixname='rateproject1', project_name='Rate project1',
                                  project_description='', neighborhood='Projects'),
                              antispam=True,
                              extra_environ=dict(username='root'), status=302)
            assert '/p/rateproject1/admin' in r.location

        # Set rate limit to 1 in first hour of user account
        with h.push_config(config, **{'project.rate_limits': '{"3600": 1}'}):
            r = self.app.post('/p/register',
                              params=dict(
                                  project_unixname='rateproject2', project_name='Rate project2',
                                  project_description='', neighborhood='Projects'),
                              antispam=True,
                              extra_environ=dict(username='root'))
            assert '/p/rateproject2/admin' in r.location

    def test_invite(self):
        p_nbhd_id = str(M.Neighborhood.query.get(name='Projects')._id)
        r = self.app.get('/adobe/_moderate/',
                         extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='adobe-1', invite='on',
                                      neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='no_such_user',
                                      invite='on', neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', invite='on',
                                      neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'invited' in r, r
        assert 'warning' not in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', invite='on',
                                      neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'warning' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', uninvite='on',
                                      neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'uninvited' in r
        assert 'warning' not in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', uninvite='on',
                                      neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'warning' in r
        r = self.app.post('/adobe/_moderate/invite',
                          params=dict(pid='test', invite='on',
                                      neighborhood_id=p_nbhd_id),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'invited' in r
        assert 'warning' not in r

    def test_evict(self):
        r = self.app.get('/adobe/_moderate/',
                         extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_moderate/evict',
                          params=dict(pid='test'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'error' in r
        r = self.app.post('/adobe/_moderate/evict',
                          params=dict(pid='adobe-1'),
                          extra_environ=dict(username='root'))
        r = self.app.get(r.location, extra_environ=dict(username='root'))
        assert 'adobe-1 evicted to Projects' in r

    def test_home(self):
        self.app.get('/adobe/')

    def test_register(self):
        r = self.app.get('/adobe/register', status=405)
        r = self.app.post('/adobe/register',
                          params=dict(
                              project_unixname='', project_name='Nothing',
                              project_description='', neighborhood='Adobe'),
                          antispam=True,
                          extra_environ=dict(username='root'))
        assert r.html.find('div', {'class': 'error'}
                           ).string == 'Please use 3-15 small letters, numbers, and dashes.'
        r = self.app.post('/adobe/register',
                          params=dict(
                              project_unixname='mymoz', project_name='My Moz',
                              project_description='', neighborhood='Adobe'),
                          antispam=True,
                          extra_environ=dict(username='*anonymous'),
                          status=302)
        r = self.app.post('/adobe/register',
                          params=dict(
                              project_unixname='foo.mymoz', project_name='My Moz',
                              project_description='', neighborhood='Adobe'),
                          antispam=True,
                          extra_environ=dict(username='root'))
        assert r.html.find('div', {'class': 'error'}
                           ).string == 'Please use 3-15 small letters, numbers, and dashes.'
        r = self.app.post('/p/register',
                          params=dict(
                              project_unixname='test', project_name='Tester',
                              project_description='', neighborhood='Projects'),
                          antispam=True,
                          extra_environ=dict(username='root'))
        assert r.html.find('div', {'class': 'error'}
                           ).string == 'This project name is taken.'
        r = self.app.post('/adobe/register',
                          params=dict(
                              project_unixname='mymoz', project_name='My Moz',
                              project_description='', neighborhood='Adobe'),
                          antispam=True,
                          extra_environ=dict(username='root'),
                          status=302)

    def test_register_private_fails_for_anon(self):
        r = self.app.post(
            '/p/register',
            params=dict(
                project_unixname='mymoz',
                project_name='My Moz',
                project_description='',
                neighborhood='Projects',
                private_project='on'),
            antispam=True,
            extra_environ=dict(username='*anonymous'),
            status=302)
        assert config.get('auth.login_url', '/auth/') in r.location, r.location

    def test_register_private_fails_for_non_admin(self):
        self.app.post(
            '/p/register',
            params=dict(
                project_unixname='mymoz',
                project_name='My Moz',
                project_description='',
                neighborhood='Projects',
                private_project='on'),
            antispam=True,
            extra_environ=dict(username='test-user'),
            status=403)

    def test_register_private_fails_for_non_private_neighborhood(self):
        # Turn off private
        neighborhood = M.Neighborhood.query.get(name='Projects')
        neighborhood.features['private_projects'] = False
        r = self.app.get('/p/add_project', extra_environ=dict(username='root'))
        assert 'canonical' in r
        assert 'private_project' not in r

        r = self.app.post(
            '/p/register',
            params=dict(
                project_unixname='myprivate1',
                project_name='My Priv1',
                project_description='',
                neighborhood='Projects',
                private_project='on'),
            antispam=True,
            extra_environ=dict(username='root'))
        cookies = r.headers.getall('Set-Cookie')
        flash_msg_cookies = list(map(six.moves.urllib.parse.unquote, cookies))

        assert any('Internal Error' in cookie for cookie in flash_msg_cookies)

        proj = M.Project.query.get(
            shortname='myprivate1', neighborhood_id=neighborhood._id)
        assert proj is None

        # Turn on private
        neighborhood = M.Neighborhood.query.get(name='Projects')
        neighborhood.features['private_projects'] = True
        r = self.app.get('/p/add_project', extra_environ=dict(username='root'))
        assert 'private_project' in r

        self.app.post(
            '/p/register',
            params=dict(
                project_unixname='myprivate2',
                project_name='My Priv2',
                project_description='',
                neighborhood='Projects',
                private_project='on'),
            antispam=True,
            extra_environ=dict(username='root'))

        proj = M.Project.query.get(
            shortname='myprivate2', neighborhood_id=neighborhood._id)
        assert proj.private

    def test_register_private_ok(self):
        r = self.app.post(
            '/p/register',
            params=dict(
                project_unixname='mymoz',
                project_name='My Moz',
                project_description='',
                neighborhood='Projects',
                private_project='on',
                tools='wiki'),
            antispam=True,
            extra_environ=dict(username='root'),
            status=302)
        assert config.get('auth.login_url',
                          '/auth/') not in r.location, r.location
        r = self.app.get(
            '/p/mymoz/wiki/',
            extra_environ=dict(username='root')).follow(extra_environ=dict(username='root'), status=200)
        r = self.app.get(
            '/p/mymoz/wiki/',
            extra_environ=dict(username='*anonymous'),
            status=302)
        assert config.get('auth.login_url', '/auth/') in r.location, r.location
        self.app.get(
            '/p/mymoz/wiki/',
            extra_environ=dict(username='test-user'),
            status=403)

    def test_project_template(self):
        setup_trove_categories()
        icon_url = 'file://' + \
                   os.path.join(allura.__path__[0], 'nf', 'allura',
                                'images', 'neo-icon-set-454545-256x350.png')
        test_groups = [{
            "name": "Viewer",  # group will be created, all params are valid
            "permissions": ["read"],
            "usernames": ["user01"]
        }, {
            "name": "",  # group won't be created - invalid name
            "permissions": ["read"],
            "usernames": ["user01"]
        }, {
            "name": "TestGroup1",  # group won't be created - invalid perm name
            "permissions": ["foobar"],
            "usernames": ["user01"]
        }, {
            "name": "TestGroup2",  # will be created; 'inspect' perm ignored
            "permissions": ["read", "inspect"],
            "usernames": ["user01", "user02"]
        }, {
            "name": "TestGroup3",  # will be created with no users in group
            "permissions": ["admin"]
        }]
        r = self.app.post('/adobe/_admin/update', params=dict(name='Mozq1',
                                                              css='',
                                                              homepage='# MozQ1!\n[Root]',
                                                              project_template="""{
                "private":true,
                "icon":{
                    "url":"%s",
                    "filename":"icon.png"
                },
                "tools":{
                    "wiki":{
                        "label":"Wiki",
                        "mount_point":"wiki",
                        "options":{
                            "show_right_bar":false,
                            "show_left_bar":false,
                            "show_discussion":false,
                            "some_url": "http://foo.com/$shortname/"
                        },
                        "home_text":"My home text!"
                    },
                    "discussion":{"label":"Discussion","mount_point":"discussion"},
                    "blog":{"label":"News","mount_point":"news","options":{
                    "show_discussion":false
                    }},
                    "admin":{"label":"Admin","mount_point":"admin"}
                },
                "tool_order":["wiki","discussion","news","admin"],
                "labels":["mmi"],
                "trove_cats":{
                    "topic":[247],
                    "developmentstatus":[11]
                },
                "groups": %s
                }""" % (icon_url, json.dumps(test_groups))),
            extra_environ=dict(username='root'))
        r = self.app.post(
            '/adobe/register',
            params=dict(
                project_unixname='testtemp',
                project_name='Test Template',
                project_description='',
                neighborhood='Mozq1',
                private_project='off'),
            antispam=True,
            extra_environ=dict(username='root'),
            status=302).follow()
        p = M.Project.query.get(shortname='testtemp')
        # make sure the correct tools got installed in the right order
        top_nav = r.html.find('div', {'id': 'top_nav'}).contents[1]
        assert top_nav.contents[1].contents[1].contents[1]['href'] == '/adobe/testtemp/wiki/'
        assert 'Wiki' in top_nav.contents[1].contents[1].contents[1].contents[0]
        assert top_nav.contents[1].contents[3].contents[1]['href'] == '/adobe/testtemp/discussion/'
        assert 'Discussion' in top_nav.contents[1].contents[3].contents[1].contents[0]
        assert top_nav.contents[1].contents[5].contents[1]['href'] == '/adobe/testtemp/news/'
        assert 'News' in top_nav.contents[1].contents[5].contents[1].contents[0]
        assert top_nav.contents[1].contents[7].contents[1]['href'] == '/adobe/testtemp/admin/'
        assert 'Admin' in top_nav.contents[1].contents[7].contents[1].contents[0]
        # make sure project is private
        r = self.app.get(
            '/adobe/testtemp/wiki/',
            extra_environ=dict(username='root')).follow(extra_environ=dict(username='root'), status=200)
        r = self.app.get(
            '/adobe/testtemp/wiki/',
            extra_environ=dict(username='*anonymous'),
            status=302)
        # check the labels and trove cats
        r = self.app.get('/adobe/testtemp/admin/trove')
        assert 'mmi' in r
        assert 'Communications » Telephony' in r
        assert '5 - Production/Stable' in r
        # check the wiki text
        r = self.app.get('/adobe/testtemp/wiki/').follow()
        assert "My home text!" in r
        # check tool options
        opts = p.app_config('wiki').options
        assert False == opts.show_discussion
        assert False == opts.show_left_bar
        assert False == opts.show_right_bar
        assert "http://foo.com/testtemp/" == opts.some_url
        # check that custom groups/perms/users were setup correctly
        roles = p.named_roles
        for group in test_groups:
            name = group.get('name')
            permissions = group.get('permissions', [])
            usernames = group.get('usernames', [])
            if name in ('Viewer', 'TestGroup2', 'TestGroup3'):
                role = M.ProjectRole.by_name(name, project=p)
                # confirm role created in project
                assert role in roles
                for perm in permissions:
                    # confirm valid permissions added to role, and invalid
                    # permissions ignored
                    if perm in p.permissions:
                        assert M.ACE.allow(role._id, perm) in p.acl
                    else:
                        assert M.ACE.allow(role._id, perm) not in p.acl
                # confirm valid users received role
                for username in usernames:
                    user = M.User.by_username(username)
                    if user and user._id:
                        assert role in M.ProjectRole.by_user(
                            user, project=p).roles
            # confirm roles with invalid json data are not created
            if name in ('', 'TestGroup1'):
                assert name not in roles

    def test_projects_anchored_tools(self):
        r = self.app.post('/adobe/_admin/update', params=dict(name='Adobe',
                                                              css='',
                                                              homepage='# Adobe!\n[Root]',
                                                              project_template="""{
                "private":true,
                "tools":{
                    "wiki":{
                        "label":"Wiki",
                        "mount_point":"wiki",
                        "options":{
                            "show_right_bar":false,
                            "show_left_bar":false,
                            "show_discussion":false,
                            "some_url": "http://foo.com/$shortname/"
                        },
                        "home_text":"My home text!"
                    },
                    "admin":{"label":"Admin","mount_point":"admin"}
                },
                "tool_order":["wiki","admin"],

                }"""),
                          extra_environ=dict(username='root'))
        neighborhood = M.Neighborhood.query.get(name='Adobe')
        neighborhood.anchored_tools = 'wiki:Wiki'
        r = self.app.post(
            '/adobe/register',
            params=dict(
                project_unixname='testtemp',
                project_name='Test Template',
                project_description='',
                neighborhood='Adobe',
                private_project='off'),
            antispam=True,
            extra_environ=dict(username='root'))
        r = self.app.get('/adobe/testtemp/admin/overview')
        assert r.html.find('div', id='top_nav').find(
            'a', href='/adobe/testtemp/wiki/'), r.html
        assert r.html.find('div', id='top_nav').find(
            'a', href='/adobe/testtemp/admin/'), r.html

    def test_name_check(self):
        for name in ('My+Moz', 'Te%st!', 'ab', 'a' * 16):
            r = self.app.get(
                '/p/check_names?neighborhood=Projects&project_unixname=%s' % name)
            assert (
                r.json ==
                {'project_unixname': 'Please use 3-15 small letters, numbers, and dashes.'})
        r = self.app.get(
            '/p/check_names?neighborhood=Projects&project_unixname=mymoz')
        assert r.json == {}
        r = self.app.get(
            '/p/check_names?neighborhood=Projects&project_unixname=test')
        assert (r.json ==
                     {'project_unixname': 'This project name is taken.'})

    @td.with_tool('test/sub1', 'Wiki', 'wiki')
    def test_neighborhood_project(self):
        self.app.get('/adobe/adobe-1/admin/', status=200)
        self.app.get('/p/test/sub1/wiki/')
        self.app.get('/p/test/sub1/', status=301)
        self.app.get('/p/test/no-such-app/', status=301)

    def test_neighborhood_namespace(self):
        # p/test exists, so try creating adobe/test
        self.app.get('/adobe/test/wiki/', status=404)
        r = self.app.post('/adobe/register',
                          params=dict(
                              project_unixname='test', project_name='Test again',
                              project_description='', neighborhood='Adobe', tools='wiki'),
                          antispam=True,
                          extra_environ=dict(username='root'))
        assert r.status_int == 302, r.html.find(
            'div', {'class': 'error'}).string
        assert not r.location.endswith('/add_project'), self.webflash(r)
        r = self.app.get('/adobe/test/wiki/').follow(status=200)

    def test_neighborhood_awards(self):
        file_name = 'adobe_icon.png'
        file_path = os.path.join(
            allura.__path__[0], 'public', 'nf', 'images', file_name)
        file_data = open(file_path, 'rb').read()
        upload = ('icon', file_name, file_data)

        r = self.app.get('/adobe/_admin/awards',
                         extra_environ=dict(username='root'))
        r = self.app.post('/adobe/_admin/awards/create',
                          params=dict(short='FOO', full='A basic foo award'),
                          extra_environ=dict(username='root'), upload_files=[upload])
        r = self.app.post('/adobe/_admin/awards/create',
                          params=dict(short='BAR',
                                      full='A basic bar award with no icon'),
                          extra_environ=dict(username='root'))
        foo_id = str(M.Award.query.find(dict(short='FOO')).first()._id)
        bar_id = str(M.Award.query.find(dict(short='BAR')).first()._id)
        r = self.app.post('/adobe/_admin/awards/%s/update' % bar_id,
                          params=dict(short='BAR2',
                                      full='Updated description.'),
                          extra_environ=dict(username='root')).follow().follow()
        assert 'BAR2' in r
        assert 'Updated description.' in r
        r = self.app.get('/adobe/_admin/awards/%s' %
                         foo_id, extra_environ=dict(username='root'))
        r = self.app.get('/adobe/_admin/awards/%s/icon' %
                         foo_id, extra_environ=dict(username='root'))
        image = PIL.Image.open(BytesIO(r.body))
        assert image.size == (48, 48)
        self.app.post('/adobe/_admin/awards/grant',
                      params=dict(grant='FOO', recipient='adobe-1',
                                  url='http://award.org', comment='Winner!'),
                      extra_environ=dict(username='root'))
        r = self.app.get('/adobe/_admin/accolades',
                         extra_environ=dict(username='root'))
        assert 'Winner!' in r
        assert 'http://award.org' in r
        self.app.get('/adobe/_admin/awards/%s/adobe-1' %
                     foo_id, extra_environ=dict(username='root'))
        self.app.post('/adobe/_admin/awards/%s/adobe-1/revoke' % foo_id,
                      extra_environ=dict(username='root'))
        self.app.post('/adobe/_admin/awards/%s/delete' % foo_id,
                      extra_environ=dict(username='root'))

    def test_add_a_project_link(self):
        from tg import tmpl_context as c
        # Install Home tool for all neighborhoods
        for nb in M.Neighborhood.query.find().all():
            p = nb.neighborhood_project
            with h.push_config(c, user=M.User.query.get()):
                p.install_app('home', 'home', 'Home', ordinal=0)
        r = self.app.get('/p/')
        assert 'Add a Project' in r
        r = self.app.get('/u/', extra_environ=dict(username='test-user'))
        assert 'Add a Project' not in r
        r = self.app.get('/adobe/', extra_environ=dict(username='test-user'))
        assert 'Add a Project' not in r
        r = self.app.get('/u/', extra_environ=dict(username='root'))
        assert 'Add a Project' in r
        r = self.app.get('/adobe/', extra_environ=dict(username='root'))
        assert 'Add a Project' in r

    def test_help(self):
        r = self.app.get('/p/_admin/help/',
                         extra_environ=dict(username='root'))
        assert 'macro' in r

    @td.with_user_project('test-user')
    def test_profile_tools(self):
        r = self.app.get('/u/test-user/',
                         extra_environ=dict(username='test-user')).follow()
        assert r.html.select('div.profile-section.tools a[href="/u/test-user/profile/"]'), r.html

    def test_user_project_creates_on_demand(self):
        M.User.register(dict(username='donald-duck'), make_project=False)
        ThreadLocalORMSession.flush_all()
        self.app.get('/u/donald-duck/')

    def test_disabled_user_has_no_user_project(self):
        M.User.register(dict(username='donald-duck'))
        self.app.get('/u/donald-duck/')  # assert it's there
        M.User.query.update(dict(username='donald-duck'),
                            {'$set': {'disabled': True}})
        self.app.get('/u/donald-duck/', status=404, extra_environ={'username': '*anonymous'})
        self.app.get('/u/donald-duck/', status=404, extra_environ={'username': 'test-user'})
        self.app.get('/u/donald-duck/', status=301, extra_environ={'username': 'test-admin'})  # site admin user

    def test_more_projects_link(self):
        r = self.app.get('/adobe/adobe-1/admin/')
        link = r.html.find(
            'div', {'class': 'neighborhood_title_link'}).find('a')
        assert 'View More Projects' in str(link)
        assert link['href'] == '/adobe/'

    def test_nav_json(self):
        self.app.get('/p/_nav.json')


class TestPhoneVerificationOnProjectRegistration(TestController):
    def test_phone_verification_fragment_renders(self):
        self.app.get('/p/phone_verification_fragment', status=200)
        self.app.get('/adobe/phone_verification_fragment', status=200)

    def test_verify_phone_no_params(self):
        with h.push_config(config, **{'project.verify_phone': 'true'}):
            self.app.get('/p/verify_phone', status=404)

    def test_verify_phone_error(self):
        with h.push_config(config, **{'project.verify_phone': 'true'}):
            r = self.app.get('/p/verify_phone', {'number': '1234567890'})
            expected = {'status': 'error',
                        'error': 'Phone service is not configured'}
            assert r.json == expected
            rid = r.session.get('phone_verification.request_id')
            hash = r.session.get('phone_verification.number_hash')
            assert rid is None
            assert hash is None

    @patch.object(g, 'phone_service', autospec=True)
    def test_verify_phone(self, phone_service):
        with h.push_config(config, **{'project.verify_phone': 'true'}):
            phone_service.verify.return_value = {
                'request_id': 'request-id', 'status': 'ok'}
            r = self.app.get('/p/verify_phone', {'number': '1-555-444-3333'})
            phone_service.verify.assert_called_once_with('15554443333')
            assert r.json == {'status': 'ok'}
            rid = r.session.get('phone_verification.request_id')
            hash = r.session.get('phone_verification.number_hash')
            assert rid == 'request-id'
            assert hash == 'f9ac49faef45d18746ced08d001e23b179107940'

    @patch.object(g, 'phone_service', autospec=True)
    def test_verify_phone_escapes_error(self, phone_service):
        phone_service.verify.return_value = {
            'status': 'error',
            'error': '<script>alert("hacked");</script>',
        }
        with h.push_config(config, **{'project.verify_phone': 'true'}):
            r = self.app.get('/p/verify_phone', {'number': '555-444-3333'})
        expected = {
            'status': 'error',
            'error': '&lt;script&gt;alert(&#34;hacked&#34;);&lt;/script&gt;',
        }
        assert r.json == expected

    @patch.object(g, 'phone_service', autospec=True)
    def test_verify_phone_already_used(self, phone_service):
        with h.push_config(config, **{'project.verify_phone': 'true'}):
            u = M.User.register(dict(username='existing-user'), make_project=False)
            u.set_tool_data('phone_verification', number_hash=utils.phone_number_hash('1-555-444-9999'))
            session(u).flush(u)
            phone_service.verify.return_value = {'request_id': 'request-id', 'status': 'ok'}
            r = self.app.get('/p/verify_phone', {'number': '1-555-444-9999'})
            assert r.json == {
                'status': 'error',
                'error': 'That phone number has already been used.'
            }

    def test_check_phone_verification_no_params(self):
        with h.push_config(config, **{'project.verify_phone': 'true'}):
            self.app.get('/p/check_phone_verification', status=404)

    @patch.object(g, 'phone_service', autospec=True)
    def test_check_phone_verification_error(self, phone_service):
        with h.push_config(config, **{'project.verify_phone': 'true'}):
            phone_service.check.return_value = {'status': 'error'}
            req_id = 'request-id'

            # make request to verify first to initialize session
            phone_service.verify.return_value = {
                'request_id': req_id, 'status': 'ok'}
            r = self.app.get('/p/verify_phone', {'number': '1234567890'})

            r = self.app.get('/p/check_phone_verification', {'pin': '1234'})
            assert r.json == {'status': 'error'}
            phone_service.check.assert_called_once_with(req_id, '1234')

            user = M.User.by_username('test-admin')
            hash = user.get_tool_data('phone_verification', 'number_hash')
            assert hash is None

    @patch.object(g, 'phone_service', autospec=True)
    def test_check_phone_verification_ok(self, phone_service):
        with h.push_config(config, **{'project.verify_phone': 'true'}):
            phone_service.check.return_value = {'status': 'ok'}
            req_id = 'request-id'

            # make request to verify first to initialize session
            phone_service.verify.return_value = {
                'request_id': req_id, 'status': 'ok'}
            r = self.app.get('/p/verify_phone', {'number': '11234567890'})

            r = self.app.get('/p/check_phone_verification', {'pin': '1234'})
            assert r.json == {'status': 'ok'}
            phone_service.check.assert_called_once_with(req_id, '1234')

            user = M.User.by_username('test-admin')
            hash = user.get_tool_data('phone_verification', 'number_hash')
            assert hash == '54c61c96d5d5aea5254c2d4f41508a938e5501b4'

    @patch.object(g, 'phone_service', autospec=True)
    def test_check_phone_verification_escapes_error(self, phone_service):
        phone_service.check.return_value = {
            'status': 'error',
            'error': '<script>alert("hacked");</script>',
        }
        with h.push_config(config, **{'project.verify_phone': 'true'}):
            r = self.app.get('/p/check_phone_verification', {'pin': '1234'})
        expected = {
            'status': 'error',
            'error': '&lt;script&gt;alert(&#34;hacked&#34;);&lt;/script&gt;',
        }
        assert r.json == expected

    def test_register_phone_not_verified(self):
        with h.push_config(config, **{'project.verify_phone': 'true'}):
            r = self.app.post(
                '/p/register',
                params=dict(
                    project_unixname='phonetest',
                    project_name='Phone Test',
                    project_description='',
                    neighborhood='Projects'),
                extra_environ=dict(username='test-user'),
                antispam=True)
            overlay = r.html.find('div', {'id': 'phone_verification_overlay'})
            assert overlay is not None
            header = overlay.find('h2')
            iframe = overlay.find('iframe')
            assert header.getText() == 'Phone Verification Required'
            assert iframe.get('src') == '/p/phone_verification_fragment'


class TestProjectImport(TestController):

    def test_not_found(self):
        self.app.get('/p/import_project/asdf/', status=404)
        self.app.get('/p/import_project/', status=404)

    # positive tests exist within ForgeImporter package
