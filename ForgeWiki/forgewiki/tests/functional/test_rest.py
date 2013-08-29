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

import json

from nose.tools import assert_equal, assert_in
import simplejson
import tg

from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase


class TestWikiApi(TestRestApiBase):

    def setUp(self):
        super(TestWikiApi, self).setUp()
        self.setup_with_tools()

    @td.with_wiki
    def setup_with_tools(self):
        h.set_context('test', 'wiki', neighborhood='Projects')

    def test_get_page(self):
        r = self.app.get('/p/test/wiki/Home/')
        discussion_url = r.html.findAll('form')[2]['action'][:-4]
        content = file(__file__).read()
        self.app.post('/wiki/Home/attach', upload_files=[('file_info', 'test_root.py', content)])
        r = self.app.get('/rest/p/test/wiki/Home/')
        r = json.loads(r.body)
        assert_equal(r['attachments'][0]['url'], 'http://localhost/p/test/wiki/Home/attachment/test_root.py')
        assert_equal(r['discussion_thread_url'], 'http://localhost/rest%s' % discussion_url)
        assert_equal(r['discussion_thread']['_id'], discussion_url.split('/')[-2])
        self.app.post('/wiki/Home/attach', upload_files=[('file_info', '__init__.py', content),])
        r = self.app.get('/rest/p/test/wiki/Home/')
        r = json.loads(r.body)
        assert_equal(len(r['attachments']), 2)

    def test_page_does_not_exist(self):
        r = self.api_get('/rest/p/test/wiki/fake/')
        assert_equal(r.status_int, 404)

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
        r = self.api_post(u'/rest/p/test/wiki/tést/'.encode('utf-8'), **data)
        assert_equal(r.status_int, 200)
        r = self.api_get(u'/rest/p/test/wiki/tést/'.encode('utf-8'))
        assert_equal(r.json['text'], data['text'])
        assert_equal(r.json['labels'], data['labels'].split(','))

    # http://blog.watchfire.com/wfblog/2011/10/json-based-xss-exploitation.html
    def test_json_encoding_security(self):
        self.api_post('/rest/p/test/wiki/foo.html',
                      text='foo <img src=x onerror=alert(1)> bar')
        r = self.api_get('/rest/p/test/wiki/foo.html')
        # raw text is not an HTML tag
        assert_in(r'foo \u003Cimg src=x onerror=alert(1)> bar', r.body)
        # and json still is parsed into correct content
        assert_equal(r.json['text'], 'foo <img src=x onerror=alert(1)> bar')

    def test_json_encoding_directly(self):
        # used in @expose('json')
        assert_equal(tg.jsonify.encode('<'), '"\u003C"')
        # make sure these are unchanged
        assert_equal(json.dumps('<'), '"<"')
        assert_equal(simplejson.dumps('<'), '"<"')
