# coding: utf-8

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
from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase
from allura import model as M
from allura.lib import helpers as h


class TestLinkApi(TestRestApiBase):

    def setUp(self):
        super(TestLinkApi, self).setUp()
        self.setup_with_tools()

    @td.with_link
    def setup_with_tools(self):
        h.set_context('test', 'link', neighborhood='Projects')

    def test_rest_link(self):
        r = self.api_get(u'/rest/p/test/link'.encode('utf-8'))
        assert_equal(r.json['url'], None)

        r = self.api_post(u'/rest/p/test/link'.encode('utf-8'),
                          url='http://google.com')
        assert_equal(r.json['url'], 'http://google.com')

        self.api_post(u'/rest/p/test/link'.encode('utf-8'),
                      url='http://yahoo.com')
        r = self.api_get(u'/rest/p/test/link'.encode('utf-8'))
        assert_equal(r.json['url'], 'http://yahoo.com')

        self.api_post(u'/rest/p/test/link'.encode('utf-8'))
        r = self.api_get(u'/rest/p/test/link'.encode('utf-8'))
        assert_equal(r.json['url'], 'http://yahoo.com')

    def test_rest_link_get_permissions(self):
        self.app.get('/rest/p/test/link',
                     extra_environ={'username': '*anonymous'}, status=200)
        p = M.Project.query.get(shortname='test')
        acl = p.app_instance('link').config.acl
        anon = M.ProjectRole.by_name('*anonymous')._id
        anon_read = M.ACE.allow(anon, 'read')
        acl.remove(anon_read)
        self.app.get('/rest/p/test/link',
                     extra_environ={'username': '*anonymous'}, status=401)

    def test_rest_link_post_permissions(self):
        self.app.post('/rest/p/test/link',
                      params={'url': 'http://yahoo.com'},
                      extra_environ={'username': '*anonymous'},
                      status=401)
        p = M.Project.query.get(shortname='test')
        acl = p.app_instance('link').config.acl
        anon = M.ProjectRole.by_name('*anonymous')._id
        anon_configure = M.ACE.allow(anon, 'configure')
        acl.append(anon_configure)
        self.app.post('/rest/p/test/link',
                      params={'url': 'http://yahoo.com'},
                      extra_environ={'username': '*anonymous'},
                      status=200)
        r = self.api_get(u'/rest/p/test/link'.encode('utf-8'))
        assert_equal(r.json['url'], 'http://yahoo.com')
