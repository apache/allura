# -*- coding: utf-8 -*-

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
from nose.tools import assert_equal, assert_in

from allura.lib import helpers as h
from allura.tests import decorators as td
from allura import model as M
from alluratest.controller import TestRestApiBase
from forgediscussion.model import ForumThread
from ming.orm import ThreadLocalORMSession


class TestDiscussionApiBase(TestRestApiBase):

    def setUp(self):
        super(TestDiscussionApiBase, self).setUp()
        self.setup_with_tools()

    @td.with_discussion
    def setup_with_tools(self):
        h.set_context('test', 'discussion', neighborhood='Projects')
        self.create_forum('héllo', 'Say Héllo', 'Say héllo here')
        self.create_topic('general', 'Let\'s talk', '1st post')
        self.create_topic('general', 'Hi guys', 'Hi boys and girls')

    def create_forum(self, shortname, name, description):
        r = self.app.get('/admin/discussion/forums')
        form = r.forms['add-forum']
        form['add_forum.shortname'] = 'héllo'
        form['add_forum.name'] = 'Say Héllo'
        form['add_forum.description'] = 'Say héllo here'
        form.submit()

    def create_topic(self, forum, subject, text):
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find(
            'form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = text
        params[f.find('select')['name']] = forum
        params[f.find('input', {'style': 'width: 90%'})['name']] = subject
        r = self.app.post('/discussion/save_new_topic', params=params)


class TestRootRestController(TestDiscussionApiBase):

    def test_forum_list(self):
        forums = self.api_get('/rest/p/test/discussion/')
        forums = forums.json['forums']
        assert_equal(len(forums), 2)
        forums = sorted(forums, key=lambda x: x['name'])
        assert_equal(forums[0]['name'], 'General Discussion')
        assert_equal(
            forums[0]['description'], 'Forum about anything you want to talk about.')
        assert_equal(forums[0]['num_topics'], 2)
        assert_equal(
            forums[0]['url'], 'http://localhost/rest/p/test/discussion/general/')
        assert_equal(forums[0]['last_post']['subject'], 'Hi guys')
        assert_equal(forums[0]['last_post']['author'], 'test-admin')
        assert_equal(forums[0]['last_post']['text'], 'Hi boys and girls')
        assert_equal(forums[1]['name'], 'Say Héllo')
        assert_equal(forums[1]['description'], 'Say héllo here')
        assert_equal(forums[1]['num_topics'], 0)
        assert_equal(
            forums[1]['url'], 'http://localhost/rest/p/test/discussion/h%C3%A9llo/')
        assert_equal(forums[1]['last_post'], None)

    def test_forum(self):
        forum = self.api_get('/rest/p/test/discussion/general/')
        forum = forum.json['forum']
        assert_equal(forum['name'], 'General Discussion')
        assert_equal(
            forum['description'], 'Forum about anything you want to talk about.')
        topics = forum['topics']
        assert_equal(len(topics), 2)
        assert_equal(topics[0]['subject'], 'Hi guys')
        assert_equal(topics[0]['num_views'], 0)
        assert_equal(topics[0]['num_replies'], 1)
        assert_equal(topics[0]['last_post']['author'], 'test-admin')
        assert_equal(topics[0]['last_post']['text'], 'Hi boys and girls')
        t = ForumThread.query.find({'subject': 'Hi guys'}).first()
        url = 'http://localhost/rest/p/test/discussion/general/thread/%s/' % t._id
        assert_equal(topics[0]['url'], url)
        assert_equal(topics[1]['subject'], 'Let\'s talk')
        assert_equal(topics[1]['num_views'], 0)
        assert_equal(topics[1]['num_replies'], 1)
        assert_equal(topics[1]['last_post']['author'], 'test-admin')
        assert_equal(topics[1]['last_post']['text'], '1st post')
        t = ForumThread.query.find({'subject': 'Let\'s talk'}).first()
        url = 'http://localhost/rest/p/test/discussion/general/thread/%s/' % t._id
        assert_equal(topics[1]['url'], url)

    def test_forum_show_ok_topics(self):
        forum = self.api_get('/rest/p/test/discussion/general/')
        forum = forum.json['forum']
        assert_equal(forum['name'], 'General Discussion')
        topics = forum['topics']
        assert_equal(len(topics), 2)
        self.create_topic('general', 'Hi again', 'It should not be shown')
        t = ForumThread.query.find({'subject': 'Hi again'}).first()
        first_post = t.first_post
        first_post.status = 'pending'
        first_post.commit()
        forum = self.api_get('/rest/p/test/discussion/general/')
        forum = forum.json['forum']
        assert_equal(forum['name'], 'General Discussion')
        topics = forum['topics']
        assert_equal(len(topics), 2)

    def test_topic(self):
        forum = self.api_get('/rest/p/test/discussion/general/')
        forum = forum.json['forum']
        assert_equal(forum['name'], 'General Discussion')
        assert_equal(
            forum['description'], 'Forum about anything you want to talk about.')
        topics = forum['topics']
        topic = self.api_get(topics[0]['url'][len('http://localhost'):])
        topic = topic.json['topic']
        assert_equal(len(topic['posts']), 1)
        assert_equal(topic['subject'], 'Hi guys')
        assert_equal(topic['posts'][0]['text'], 'Hi boys and girls')
        assert_equal(topic['posts'][0]['subject'], 'Hi guys')
        assert_in('timestamp', topic['posts'][0])
        assert_in('last_edited', topic['posts'][0])

    def test_forum_list_pagination(self):
        resp = self.app.get('/rest/p/test/discussion/?limit=1')
        forums = resp.json['forums']
        assert_equal(len(forums), 1)
        assert_equal(forums[0]['name'], 'General Discussion')
        assert_equal(resp.json['count'], 2)
        assert_equal(resp.json['page'], 0)
        assert_equal(resp.json['limit'], 1)
        resp = self.app.get('/rest/p/test/discussion/?limit=1&page=1')
        forums = resp.json['forums']
        assert_equal(len(forums), 1)
        assert_equal(forums[0]['name'], 'Say Héllo')
        assert_equal(resp.json['count'], 2)
        assert_equal(resp.json['page'], 1)
        assert_equal(resp.json['limit'], 1)

    def test_forum_pagination(self):
        resp = self.app.get('/rest/p/test/discussion/general/?limit=1')
        topics = resp.json['forum']['topics']
        assert_equal(len(topics), 1)
        assert_equal(topics[0]['subject'], 'Hi guys')
        assert_equal(resp.json['count'], 2)
        assert_equal(resp.json['page'], 0)
        assert_equal(resp.json['limit'], 1)
        resp = self.app.get('/rest/p/test/discussion/general/?limit=1&page=1')
        topics = resp.json['forum']['topics']
        assert_equal(len(topics), 1)
        assert_equal(topics[0]['subject'], 'Let\'s talk')
        assert_equal(resp.json['count'], 2)
        assert_equal(resp.json['page'], 1)
        assert_equal(resp.json['limit'], 1)

    def test_topic_pagination(self):
        thread = ForumThread.query.find({'subject': 'Hi guys'}).first()
        thread.post('Hi guy', 'I am second post')
        url = '/rest/p/test/discussion/general/thread/%s/' % thread._id
        resp = self.app.get(url + '?limit=1')
        posts = resp.json['topic']['posts']
        assert_equal(len(posts), 1)
        assert_equal(posts[0]['text'], 'Hi boys and girls')
        assert_equal(resp.json['count'], 2)
        assert_equal(resp.json['page'], 0)
        assert_equal(resp.json['limit'], 1)
        resp = self.app.get(url + '?limit=1&page=1')
        posts = resp.json['topic']['posts']
        assert_equal(len(posts), 1)
        assert_equal(posts[0]['text'], 'I am second post')
        assert_equal(resp.json['count'], 2)
        assert_equal(resp.json['page'], 1)
        assert_equal(resp.json['limit'], 1)

    def test_topic_show_ok_only(self):
        thread = ForumThread.query.find({'subject': 'Hi guys'}).first()
        url = '/rest/p/test/discussion/general/thread/%s/' % thread._id
        resp = self.app.get(url)
        posts = resp.json['topic']['posts']
        assert_equal(len(posts), 1)
        thread.post('Hello', 'I am not ok post')
        last_post = thread.last_post
        last_post.status = 'pending'
        last_post.commit()
        ThreadLocalORMSession.flush_all()
        resp = self.app.get(url)
        posts = resp.json['topic']['posts']
        assert_equal(len(posts), 1)

    def test_security(self):
        p = M.Project.query.get(shortname='test')
        acl = p.app_instance('discussion').config.acl
        anon = M.ProjectRole.by_name('*anonymous')._id
        auth = M.ProjectRole.by_name('*authenticated')._id
        anon_read = M.ACE.allow(anon, 'read')
        auth_read = M.ACE.allow(auth, 'read')
        acl.remove(anon_read)
        acl.append(auth_read)
        self.api_get('/rest/p/test/discussion/')
        self.app.get('/rest/p/test/discussion/',
                     extra_environ={'username': str('*anonymous')},
                     status=401)
        self.api_get('/rest/p/test/discussion/general/')
        self.app.get('/rest/p/test/discussion/general/',
                     extra_environ={'username': str('*anonymous')},
                     status=401)
        t = ForumThread.query.find({'subject': 'Hi guys'}).first()
        self.api_get('/rest/p/test/discussion/general/thread/%s/' % t._id)
        self.app.get('/rest/p/test/discussion/general/thread/%s/' % t._id,
                     extra_environ={'username': str('*anonymous')},
                     status=401)

    def test_private_forums(self):
        r = self.app.get('/p/test/admin/discussion/forums')
        form = r.forms['edit-forums']
        if form['forum-0.shortname'].value == 'héllo':
            form['forum-0.members_only'] = True
        else:
            form['forum-1.members_only'] = True
        form.submit()
        r = self.api_get('/rest/p/test/discussion/')
        assert_equal(len(r.json['forums']), 2)
        r = self.app.get('/rest/p/test/discussion/',
                         extra_environ={'username': str('*anonymous')})
        assert_equal(len(r.json['forums']), 1)
        assert_equal(r.json['forums'][0]['shortname'], 'general')

    def test_has_access_no_params(self):
        self.api_get('/rest/p/test/discussion/has_access', status=404)
        self.api_get('/rest/p/test/discussion/has_access?user=root', status=404)
        self.api_get('/rest/p/test/discussion/has_access?perm=read', status=404)

    def test_has_access_unknown_params(self):
        """Unknown user and/or permission always False for has_access API"""
        r = self.api_get(
            '/rest/p/test/discussion/has_access?user=babadook&perm=read',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
        r = self.api_get(
            '/rest/p/test/discussion/has_access?user=test-user&perm=jump',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)

    def test_has_access_not_admin(self):
        """
        User which has no 'admin' permission on neighborhood can't use
        has_access API
        """
        self.api_get(
            '/rest/p/test/discussion/has_access?user=test-admin&perm=admin',
            user='test-user',
            status=403)

    def test_has_access(self):
        r = self.api_get(
            '/rest/p/test/discussion/has_access?user=test-admin&perm=post',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], True)
        r = self.api_get(
            '/rest/p/test/discussion/has_access?user=*anonymous&perm=admin',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
