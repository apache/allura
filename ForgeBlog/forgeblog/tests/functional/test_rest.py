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
from datetime import date

import tg
from nose.tools import assert_equal, assert_in

from allura.lib import helpers as h
from allura.tests import decorators as td
from allura import model as M
from alluratest.controller import TestRestApiBase

from forgeblog import model as BM


class TestBlogApi(TestRestApiBase):

    def setUp(self):
        super(TestBlogApi, self).setUp()
        self.setup_with_tools()

    @td.with_tool('test', 'Blog', 'blog')
    def setup_with_tools(self):
        h.set_context('test', 'blog', neighborhood='Projects')

    def test_create_post(self):
        data = {
            'title': 'test',
            'text': 'test text',
            'state': 'published',
            'labels': 'label1, label2'
        }
        r = self.api_post('/rest/p/test/blog/', **data)
        assert_equal(
            r.location, 'http://localhost/rest/p/test/blog/%s/%s/test/' %
            (date.today().strftime("%Y"), date.today().strftime("%m")))
        assert_equal(r.status_int, 201)
        url = '/rest' + BM.BlogPost.query.find().first().url()
        r = self.api_get('/rest/p/test/blog/')
        assert_equal(r.json['posts'][0]['title'], 'test')
        assert_in(url, r.json['posts'][0]['url'])

        r = self.api_get(url)
        assert_equal(r.json['title'], data['title'])
        assert_equal(r.json['text'], data['text'])
        assert_equal(r.json['author'], 'test-admin')
        assert_equal(r.json['state'], data['state'])
        assert_equal(r.json['labels'], data['labels'].split(','))

    def test_update_post(self):
        data = {
            'title': 'test',
            'text': 'test text',
            'state': 'published',
            'labels': 'label1, label2'
        }
        r = self.api_post('/rest/p/test/blog/', **data)
        assert_equal(r.status_int, 201)
        url = '/rest' + BM.BlogPost.query.find().first().url()
        data = {
            'text': 'test text2',
            'state': 'draft',
            'labels': 'label3'
        }
        self.api_post(url, **data)
        r = self.api_get(url)
        assert_equal(r.json['title'], 'test')
        assert_equal(r.json['text'], data['text'])
        assert_equal(r.json['state'], data['state'])
        assert_equal(r.json['labels'], data['labels'].split(','))

    def test_delete_post(self):
        data = {
            'title': 'test',
            'state': 'published',
            'labels': 'label1, label2'
        }
        r = self.api_post('/rest/p/test/blog/', **data)
        assert_equal(r.status_int, 201)
        url = '/rest' + BM.BlogPost.query.find().first().url()
        self.api_post(url, delete='')
        r = self.api_get(url, status=404)

    def test_post_does_not_exist(self):
        r = self.api_get('/rest/p/test/blog/2013/07/fake/', status=404)

    def test_read_permissons(self):
        self.api_post('/rest/p/test/blog/', title='test',
                      text='test text', state='published')
        self.app.get('/rest/p/test/blog/',
                     extra_environ={'username': str('*anonymous')}, status=200)
        p = M.Project.query.get(shortname='test')
        acl = p.app_instance('blog').config.acl
        anon = M.ProjectRole.by_name('*anonymous')._id
        anon_read = M.ACE.allow(anon, 'read')
        acl.remove(anon_read)
        self.app.get('/rest/p/test/blog/',
                     extra_environ={'username': str('*anonymous')},
                     status=401)

    def test_new_post_permissons(self):
        self.app.post('/rest/p/test/blog/',
                      params=dict(title='test', text='test text',
                                  state='published'),
                      extra_environ={'username': str('*anonymous')},
                      status=401)
        p = M.Project.query.get(shortname='test')
        acl = p.app_instance('blog').config.acl
        anon = M.ProjectRole.by_name('*anonymous')._id
        anon_write = M.ACE.allow(anon, 'write')
        acl.append(anon_write)
        self.app.post('/rest/p/test/blog/',
                      params=dict(title='test', text='test text',
                                  state='published'),
                      extra_environ={'username': str('*anonymous')},
                      status=201)

    def test_update_post_permissons(self):
        self.api_post('/rest/p/test/blog/', title='test',
                      text='test text', state='published')
        url = '/rest' + BM.BlogPost.query.find().first().url()
        self.app.post(url.encode('utf-8'),
                      params=dict(title='test2', text='test text2',
                                  state='published'),
                      extra_environ={'username': str('*anonymous')},
                      status=401)
        p = M.Project.query.get(shortname='test')
        acl = p.app_instance('blog').config.acl
        anon = M.ProjectRole.by_name('*anonymous')._id
        anon_write = M.ACE.allow(anon, 'write')
        acl.append(anon_write)
        self.app.post(url.encode('utf-8'),
                      params=dict(title='test2', text='test text2',
                                  state='published'),
                      extra_environ={'username': str('*anonymous')},
                      status=200)
        r = self.api_get(url)
        assert_equal(r.json['title'], 'test2')
        assert_equal(r.json['text'], 'test text2')
        assert_equal(r.json['state'], 'published')

    def test_permission_draft_post(self):
        self.api_post('/rest/p/test/blog/', title='test',
                      text='test text', state='draft')
        r = self.app.get('/rest/p/test/blog/',
                         extra_environ={'username': str('*anonymous')})
        assert_equal(r.json['posts'], [])
        url = '/rest' + BM.BlogPost.query.find().first().url()
        self.app.post(url.encode('utf-8'),
                      params=dict(title='test2', text='test text2',
                                  state='published'),
                      extra_environ={'username': str('*anonymous')},
                      status=401)
        p = M.Project.query.get(shortname='test')
        acl = p.app_instance('blog').config.acl
        anon = M.ProjectRole.by_name('*anonymous')._id
        anon_write = M.ACE.allow(anon, 'write')
        acl.append(anon_write)
        r = self.app.get('/rest/p/test/blog/',
                         extra_environ={'username': str('*anonymous')})
        assert_equal(r.json['posts'][0]['title'], 'test')

    def test_draft_post(self):
        self.api_post('/rest/p/test/blog/', title='test',
                      text='test text', state='draft')
        r = self.app.get('/rest/p/test/blog/',
                         extra_environ={'username': str('*anonymous')})
        assert_equal(r.json['posts'], [])
        url = '/rest' + BM.BlogPost.query.find().first().url()
        self.api_post(url, state='published')
        r = self.app.get('/rest/p/test/blog/',
                         extra_environ={'username': str('*anonymous')})
        assert_equal(r.json['posts'][0]['title'], 'test')

    def test_pagination(self):
        self.api_post('/rest/p/test/blog/', title='test1',
                      text='test text1', state='published')
        self.api_post('/rest/p/test/blog/', title='test2',
                      text='test text2', state='published')
        self.api_post('/rest/p/test/blog/', title='test3',
                      text='test text3', state='published')
        r = self.api_get('/rest/p/test/blog/', limit='1', page='0')
        assert_equal(r.json['posts'][0]['title'], 'test3')
        assert_equal(len(r.json['posts']), 1)
        assert_equal(r.json['count'], 3)
        assert_equal(r.json['limit'], 1)
        assert_equal(r.json['page'], 0)
        r = self.api_get('/rest/p/test/blog/', limit='2', page='0')
        assert_equal(r.json['posts'][0]['title'], 'test3')
        assert_equal(r.json['posts'][1]['title'], 'test2')
        assert_equal(len(r.json['posts']), 2)
        assert_equal(r.json['count'], 3)
        assert_equal(r.json['limit'], 2)
        assert_equal(r.json['page'], 0)
        r = self.api_get('/rest/p/test/blog/', limit='1', page='2')
        assert_equal(r.json['posts'][0]['title'], 'test1')
        assert_equal(r.json['count'], 3)
        assert_equal(r.json['limit'], 1)
        assert_equal(r.json['page'], 2)

    def test_has_access_no_params(self):
        self.api_get('/rest/p/test/blog/has_access', status=404)
        self.api_get('/rest/p/test/blog/has_access?user=root', status=404)
        self.api_get('/rest/p/test/blog/has_access?perm=read', status=404)

    def test_has_access_unknown_params(self):
        """Unknown user and/or permission always False for has_access API"""
        r = self.api_get(
            '/rest/p/test/blog/has_access?user=babadook&perm=read',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
        r = self.api_get(
            '/rest/p/test/blog/has_access?user=test-user&perm=jump',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)

    def test_has_access_not_admin(self):
        """
        User which has no 'admin' permission on neighborhood can't use
        has_access API
        """
        self.api_get(
            '/rest/p/test/blog/has_access?user=test-admin&perm=admin',
            user='test-user',
            status=403)

    def test_has_access(self):
        r = self.api_get(
            '/rest/p/test/blog/has_access?user=test-admin&perm=post&access_token=ABCDEF',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], True)
        r = self.api_get(
            '/rest/p/test/blog/has_access?user=*anonymous&perm=admin',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)

    def test_create_post_limit_by_project(self):
        data = {
            'title': 'test against limit',
            'text': 'test text',
            'state': 'published',
            'labels': 'label1, label2'
        }
        # Set rate limit to 0 in first hour of project
        with h.push_config(tg.config, **{'forgeblog.rate_limits': '{"3600": 0}'}):
            self.api_post('/rest/p/test/blog/', status=429, **data)

    def test_edit_post_limit_by_user(self):
        data = {
            'title': 'test abc',
            'text': 'test text',
            'state': 'published',
            'labels': 'label1, label2'
        }
        self.api_post('/rest/p/test/blog/', status=201, **data)

        url = '/rest' + BM.BlogPost.query.find().first().url()
        data = {
            'text': 'test xyz',
            'state': 'published',
            'labels': 'label3'
        }
        # Set rate limit to 1 in first hour of user
        with h.push_config(tg.config, **{'forgeblog.rate_limits_per_user': '{"3600": 1}'}):
            self.api_post(url, status=429, **data)
