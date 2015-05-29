from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from __future__ import unicode_literals
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

from nose.tools import assert_equal

from allura import model as M
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
        redirected = self.app.get('/link/index').follow()
        assert redirected.request.url == 'http://www.google.com/'

    @td.with_link
    def test_root_with_url(self):
        response = self.app.get('/admin/link/options', validate_chunk=True)
        response.form['url'] = 'http://www.google.com/'
        response.form.submit()
        redirected = self.app.get('/link').follow()
        assert redirected.request.url == 'http://www.google.com/'

    @td.with_link
    def test_root_suffix_with_url_slash(self):
        response = self.app.get('/admin/link/options', validate_chunk=True)
        response.form['url'] = 'http://www.google.com/'
        response.form.submit()
        redirected = self.app.get('/link/service')
        # HACK: support for remote redirects is limited in follow()
        assert 'http://www.google.com/service' in redirected

    @td.with_link
    def test_root_suffix_with_url_value(self):
        response = self.app.get('/admin/link/options', validate_chunk=True)
        response.form['url'] = 'http://www.google.de/search?q='
        response.form.submit()
        response = self.app.get('/link/help')
        # HACK: support for remote redirects is limited in follow()
        assert 'http://www.google.de/search?q=help' in response

    @td.with_link
    def test_set_url_validation(self):
        r = self.app.post('/p/test/admin/link/set_url', {})
        expected = {'status': 'error',
                    'errors': {'url': 'Please enter a value'}}
        assert_equal(r.json, expected)

        r = self.app.post('/p/test/admin/link/set_url', {'url': ''})
        expected = {'status': 'error',
                    'errors': {'url': 'Please enter a value'}}
        assert_equal(r.json, expected)

        r = self.app.post('/p/test/admin/link/set_url', {'url': 'bad url'})
        expected = {'status': 'error',
                    'errors': {'url': 'That is not a valid URL'}}
        assert_equal(r.json, expected)

        p = M.Project.query.get(shortname='test')
        link = p.app_instance('link')
        assert_equal(link.config.options.get('url'), None)

    @td.with_link
    def test_set_url(self):
        data = {'url': 'http://example.com'}  # http
        r = self.app.post('/p/test/admin/link/set_url', data)
        assert_equal(r.json, {'status': 'ok'})
        p = M.Project.query.get(shortname='test')
        link = p.app_instance('link')
        assert_equal(link.config.options.get('url'), 'http://example.com')

        data = {'url': 'https://google.com'}  # https
        r = self.app.post('/p/test/admin/link/set_url', data)
        assert_equal(r.json, {'status': 'ok'})
        p = M.Project.query.get(shortname='test')
        link = p.app_instance('link')
        assert_equal(link.config.options.get('url'), 'https://google.com')

        data = {'url': 'lmgtfy.com'}  # http is added if not provided
        r = self.app.post('/p/test/admin/link/set_url', data)
        assert_equal(r.json, {'status': 'ok'})
        p = M.Project.query.get(shortname='test')
        link = p.app_instance('link')
        assert_equal(link.config.options.get('url'), 'http://lmgtfy.com')
