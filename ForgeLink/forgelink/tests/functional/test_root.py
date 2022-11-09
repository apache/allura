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

from allura import model as M
from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import TestController


class TestRootController(TestController):

    def test_root_index_no_url(self):
        response = self.app.get('/link/index')
        assert 'Link is not configured' in response

    @td.with_link
    def test_root_index_with_url(self):
        response = self.app.get('/admin/link/options', validate_chunk=True)
        response.form['url'] = 'http://www.google.com/'
        response.form.submit()
        redir = self.app.get('/link/index', status=302)
        assert redir.location == 'http://www.google.com/'

    @td.with_link
    def test_root_with_url(self):
        response = self.app.get('/admin/link/options', validate_chunk=True)
        response.form['url'] = 'http://www.google.com/'
        response.form.submit()
        redir = self.app.get('/link', status=302)
        assert redir.location == 'http://www.google.com/'

    @td.with_link
    def test_root_suffix_with_url_slash(self):
        response = self.app.get('/admin/link/options', validate_chunk=True)
        response.form['url'] = 'http://www.google.com/'
        response.form.submit()
        redir = self.app.get('/link/service', status=302)
        assert redir.location == 'http://www.google.com/service'

    @td.with_link
    def test_root_suffix_with_url_value(self):
        response = self.app.get('/admin/link/options', validate_chunk=True)
        response.form['url'] = 'http://www.google.de/search?q='
        response.form.submit()
        redir = self.app.get(h.urlquote('/link/helpåß'), status=302)
        assert redir.location == 'http://www.google.de/search?q=help%C3%A5%C3%9F'


class TestConfigOptions(TestController):

    @property
    def project(self):
        return M.Project.query.get(shortname='test')

    def assert_url(self, mount_point, val):
        app = self.project.app_instance(mount_point)
        assert app.config.options['url'] == val

    def test_sets_url_on_install(self):
        r = self.app.post('/p/test/admin/update_mounts', params={
            'new.install': 'install',
            'new.ep_name': 'link',
            'new.ordinal': '1',
            'new.mount_point': 'link-google',
            'new.mount_label': 'Google',
            'url': 'google.com'})
        self.assert_url('link-google', 'http://google.com')

    def test_validates_url_on_install(self):
        r = self.app.post('/p/test/admin/update_mounts', params={
            'new.install': 'install',
            'new.ep_name': 'link',
            'new.ordinal': '1',
            'new.mount_point': 'link-google',
            'new.mount_label': 'Google',
            'url': 'invalid url'})
        flash = json.loads(self.webflash(r))
        assert flash['status'] == 'error'
        assert flash['message'] == 'ToolError: url: That is not a valid URL'
        app = self.project.app_instance('link-google')
        assert app is None

    @td.with_link
    def test_sets_url_on_config(self):
        self.assert_url('link', None)
        params = {'url': 'https://allura.apache.org'}
        r = self.app.post('/p/test/admin/link/configure', params=params)
        assert self.webflash(r) == ''
        self.assert_url('link', 'https://allura.apache.org')

    @td.with_link
    def test_validates_url_on_config(self):
        self.assert_url('link', None)
        params = {'url': 'invalid link'}
        r = self.app.post('/p/test/admin/link/configure', params=params)
        flash = json.loads(self.webflash(r))
        assert flash['status'] == 'error'
        assert flash['message'] == 'url: That is not a valid URL'
        self.assert_url('link', None)

    @td.with_link
    def test_menu_url(self):
        resp = self.app.get('/p/test/admin/')
        assert '/p/test/link/' in str(resp.html.find(id='top_nav'))

        response = self.app.get('/admin/link/options')
        response.form['url'] = 'http://foo.bar/baz'
        response.form.submit()

        resp = self.app.get('/p/test/admin/')
        assert 'http://foo.bar/baz' in str(resp.html.find(id='top_nav'))

    def _check_configurable(self, admin_nav_data):
        for menu_item in admin_nav_data['menu']:
            if menu_item['tool_name'] == 'link':
                assert ({'className': 'admin_modal',
                           'text': 'Options',
                           'href': '/p/test/admin/link/options'} in
                          menu_item['admin_options'])
                break
        else:
            raise AssertionError("Didn't find 'link' tool in {}".format(admin_nav_data['menu']))

    @td.with_link
    def test_menu_configurable(self):
        admin_nav_data = self.app.get('/p/test/_nav.json?admin_options=true').json
        self._check_configurable(admin_nav_data)

        response = self.app.get('/admin/link/options')
        response.form['url'] = 'http://foo.bar/baz'
        response.form.submit()

        admin_nav_data = self.app.get('/p/test/_nav.json?admin_options=true').json
        self._check_configurable(admin_nav_data)
