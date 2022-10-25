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

from tg import tmpl_context as c
from tg import config
import mock

from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import TestController

from forgeshorturl.model import ShortUrl


class TestRootController(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        self.setup_with_tools()

    @td.with_url
    def setup_with_tools(self):
        pass

    def test_shorturl_add(self):
        response = self.app.get('/admin/url/add')
        response.form['short_url'] = 'test'
        response.form['full_url'] = 'http://www.google.com/'
        response.form.submit()
        redir = self.app.get('/url/test', status=302)
        assert redir.location == 'http://www.google.com/'

    def test_shorturl_http_head(self):
        response = self.app.get('/admin/url/add')
        response.form['short_url'] = 'test'
        response.form['full_url'] = 'http://www.google.com/'
        response.form.submit()
        r = self.app.head('/url/test', status=302)
        assert r.location == 'http://www.google.com/'

    def test_shorturl_update(self):
        response = self.app.get('/admin/url/add')
        response.form['short_url'] = 'g'
        response.form['full_url'] = 'http://www.google.com/'
        response.form.submit()
        redir = self.app.get('/url/g', status=302)
        assert redir.location == 'http://www.google.com/'

        response = self.app.get('/url/')
        form = response.forms['short-url-form']
        form['update'] = 'True'
        form['short_url'] = 'g'
        form['full_url'] = 'http://www.yahoo.com/'
        form.action = '/admin/url/add/'
        form.submit()
        redir = self.app.get('/url/g', status=302)
        assert redir.location == 'http://www.yahoo.com/'

    def test_shorturl_not_found(self):
        self.app.post('/admin/url/add',
                      dict(short_url='test',
                           full_url='http://www.google.com/',
                           description="description2"))
        r = self.app.get('/url/test2', status=404)
        r = self.app.get('/url/')
        assert 'http://www.google.com/' in r

    def test_shorturl_private(self):
        self.app.post('/admin/url/add',
                      dict(short_url='test_private',
                           full_url='http://www.amazone.com/',
                           private='on',
                           description="description1"))
        r = self.app.get('/url/')
        assert 'http://www.amazone.com/' in r
        assert '<td><small>yes</small></td>' in r
        self.app.get('/url/test_private',
                     extra_environ=dict(username='*anonymous'),
                     status=404)
        self.app.get('/url/test_private',
                     status=302)

    def test_shorturl_errors(self):
        d = dict(short_url='amazone',
                 full_url='amazone')
        r = self.app.post('/admin/url/add', params=d)
        assert 'error' in self.webflash(r)
        d = dict(short_url='test', full_url='http://google.com/')
        r = self.app.post('/admin/url/add', params=d)
        d['full_url'] = 'http://yahoo.com'
        r = self.app.post('/admin/url/add', params=d)
        assert 'exists' in self.webflash(r)

    def test_shorturl_chars_restrictions(self):
        d = dict(short_url='', full_url='http://domain.net/')
        r = self.app.post('/admin/url/add', params=d)
        assert ShortUrl.query.find(
            dict(app_config_id=c.app.config._id)).count() == 0
        assert 'Please enter a value' in self.webflash(r)
        d = dict(short_url='g*', full_url='http://domain.net/')
        r = self.app.post('/admin/url/add', params=d)
        assert ShortUrl.query.find(
            dict(app_config_id=c.app.config._id)).count() == 0
        assert 'Short url: must include only letters, numbers, dashes and underscores.' in self.webflash(
            r)

    def test_shorturl_remove(self):
        self.app.post('/admin/url/add',
                      params=dict(short_url='g', full_url='http://google.com/'))
        assert ShortUrl.query.find(
            dict(app_config_id=c.app.config._id)).count() == 1
        self.app.post('/admin/url/remove', params=dict(shorturl='g'))
        assert ShortUrl.query.find(
            dict(app_config_id=c.app.config._id)).count() == 0

    def test_shorturl_permissions(self):
        self.app.post('/admin/url/add',
                      params=dict(short_url='g',
                                  full_url='http://google.com/'),
                      extra_environ=dict(username='test-user'), status=403)
        self.app.post('/admin/url/remove', params=dict(shorturl='g'),
                      extra_environ=dict(username='test-user'), status=403)

    def test_build_short_url(self):
        with h.push_config(config, **{
                'short_url.url_pattern': '{base_url}:{nbhd}:{project}:{mount_point}:{short_name}',
                'base_url': 'b',
        }):
            nbhd = mock.Mock(url_prefix='/n/')
            project = mock.Mock(shortname='p', neighborhood=nbhd)
            app = mock.Mock(project=project)
            app.config.options.mount_point = 'm'

            url = ShortUrl.build_short_url(app, 's')

            assert url == 'b:n:p:m:s'

    def test_short_url(self):
        response = self.app.get('/admin/url/add')
        response.form['short_url'] = 'test'
        response.form['full_url'] = 'http://www.google.com/'
        response.form.submit()

        surl = ShortUrl.query.get(short_name='test')

        with h.push_config(config, **{
                'short_url.url_pattern': '{base_url}:{nbhd}:{project}:{mount_point}:{short_name}',
                'base_url': 'b',
        }):
            assert surl.short_url() == 'b:p:test:url:test'
