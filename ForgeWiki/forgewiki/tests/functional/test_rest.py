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

from __future__ import unicode_literals
from __future__ import absolute_import
import json
from io import open

from nose.tools import assert_equal, assert_in, assert_not_equal
import tg

from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase

from forgewiki.model import Page


class TestWikiApi(TestRestApiBase):

    def setUp(self):
        super(TestWikiApi, self).setUp()
        self.setup_with_tools()

    @td.with_wiki
    def setup_with_tools(self):
        h.set_context('test', 'wiki', neighborhood='Projects')

    def test_get_root(self):
        r = self.app.get('/rest/p/test/wiki/')
        assert_equal(r.json, {'pages': ['Home']})

    def test_get_page(self):
        r = self.app.get('/p/test/wiki/Home/')
        discussion_url = r.html.find('form', id='edit_post')['action'][:-4]
        content = open(__file__, 'rb').read()
        self.app.post('/wiki/Home/attach',
                      upload_files=[('file_info', 'test_root.py', content)])
        r = self.app.get('/rest/p/test/wiki/Home/')
        r = json.loads(r.text)
        assert_equal(r['attachments'][0]['url'],
                     'http://localhost/p/test/wiki/Home/attachment/test_root.py')
        assert_equal(r['discussion_thread_url'], 'http://localhost/rest%s' %
                     discussion_url)
        assert_equal(r['discussion_thread']['_id'],
                     discussion_url.split('/')[-2])
        self.app.post('/wiki/Home/attach',
                      upload_files=[('file_info', '__init__.py', content), ])
        r = self.app.get('/rest/p/test/wiki/Home/')
        r = json.loads(r.text)
        assert_equal(len(r['attachments']), 2)

    def test_page_does_not_exist(self):
        r = self.api_get('/rest/p/test/wiki/fake/', status=404)

    def test_update_page(self):
        data = {
            'text': 'Embrace the Dark Side',
            'labels': 'head hunting,dark side'
        }
        r = self.api_post('/rest/p/test/wiki/Home/', **data)
        assert_equal(r.status_int, 200)
        r = self.api_get('/rest/p/test/wiki/Home/')
        assert_equal(r.json['text'], data['text'])
        assert_equal(r.json['labels'], data['labels'].split(','))

    def test_create_page(self):
        data = {
            'text': 'Embrace the Dark Side',
            'labels': 'head hunting,dark side'
        }
        r = self.api_post('/rest/p/test/wiki/tést/'.encode('utf-8'), **data)
        assert_equal(r.status_int, 200)
        r = self.api_get('/rest/p/test/wiki/tést/'.encode('utf-8'))
        assert_equal(r.json['text'], data['text'])
        assert_equal(r.json['labels'], data['labels'].split(','))

    def test_create_page_limit(self):
        data = {
            'text': 'Embrace the Dark Side',
            'labels': 'head hunting,dark side'
        }
        # Set rate limit to unlimit
        with h.push_config(tg.config, **{'forgewiki.rate_limits': '{}'}):
            r = self.api_post('/rest/p/test/wiki/page1/', status=200, **data)
            p = Page.query.get(title='page1')
            assert_not_equal(p, None)
        # Set rate limit to 1 in first hour of project
        with h.push_config(tg.config, **{'forgewiki.rate_limits': '{"3600": 1}'}):
            r = self.api_post('/rest/p/test/wiki/page2/', status=429, **data)
            p = Page.query.get(title='page2')
            assert_equal(p, None)

    # http://blog.watchfire.com/wfblog/2011/10/json-based-xss-exploitation.html
    def test_json_encoding_security(self):
        self.api_post('/rest/p/test/wiki/foo.html',
                      text='foo <img src=x onerror=alert(1)> bar')
        r = self.api_get('/rest/p/test/wiki/foo.html')
        # raw text is not an HTML tag
        assert_in(r'foo \u003Cimg src=x onerror=alert(1)> bar', r.text)
        # and json still is parsed into correct content
        assert_equal(r.json['text'], 'foo <img src=x onerror=alert(1)> bar')

    def test_json_encoding_directly(self):
        # used in @expose('json'), monkey-patched in our patches.py
        assert_equal(tg.jsonify.encode('<'), '"\u003C"')
        # make sure these are unchanged
        assert_equal(json.dumps('<'), '"<"')


class TestWikiHasAccess(TestRestApiBase):

    def setUp(self):
        super(TestWikiHasAccess, self).setUp()
        self.setup_with_tools()

    @td.with_wiki
    def setup_with_tools(self):
        h.set_context('test', 'wiki', neighborhood='Projects')

    def test_has_access_no_params(self):
        self.api_get('/rest/p/test/wiki/has_access', status=404)
        self.api_get('/rest/p/test/wiki/has_access?user=root', status=404)
        self.api_get('/rest/p/test/wiki/has_access?perm=read', status=404)

    def test_has_access_unknown_params(self):
        """Unknown user and/or permission always False for has_access API"""
        r = self.api_get(
            '/rest/p/test/wiki/has_access?user=babadook&perm=read',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
        r = self.api_get(
            '/rest/p/test/wiki/has_access?user=test-user&perm=jump',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)

    def test_has_access_not_admin(self):
        """
        User which has no 'admin' permission on neighborhood can't use
        has_access API
        """
        self.api_get(
            '/rest/p/test/wiki/has_access?user=test-admin&perm=admin',
            user='test-user',
            status=403)

    def test_has_access(self):
        r = self.api_get(
            '/rest/p/test/wiki/has_access?user=test-admin&perm=create',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], True)
        r = self.api_get(
            '/rest/p/test/wiki/has_access?user=test-user&perm=create',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
