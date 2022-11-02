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

import mock
import pytest
import random
import logging
from six.moves.email_mime_text import MIMEText
from six.moves.email_mime_image import MIMEImage
from six.moves.email_mime_multipart import MIMEMultipart

import pkg_resources
import pymongo
import webtest

from ming.odm import ThreadLocalORMSession
from tg import tmpl_context as c
from tg import config

import feedparser

from allura import model as M
from allura.tasks import mail_tasks
from alluratest.controller import TestController
from allura.lib import helpers as h
from allura.tests import decorators as td

from forgediscussion import model as FM

log = logging.getLogger(__name__)


class TestForumEmail(TestController):
    def setup_method(self, method):
        super().setup_method(method)
        c.user = M.User.by_username('test-admin')
        self.app.get('/discussion/')
        r = self.app.get('/admin/discussion/forums')
        form = r.forms['add-forum']
        form['add_forum.shortname'] = 'testforum'
        form['add_forum.name'] = 'Test Forum'
        form.submit()
        r = self.app.get('/admin/discussion/forums')
        assert 'testforum' in r
        self.email_address = c.user.email_addresses[0]
        h.set_context('test', 'discussion', neighborhood='Projects')
        self.forum = FM.Forum.query.get(shortname='testforum')

    def test_simple_email(self):
        msg = MIMEText('This is a test message')
        self._post_email(
            self.email_address,
            [self.forum.email_address],
            'Test Simple Thread',
            msg)
        r = self.app.get('/p/test/discussion/testforum/')
        assert 'Test Simple Thread' in str(r)

    def test_html_email(self):
        msg = MIMEMultipart(
            'alternative',
            _subparts=[
                MIMEText('This is a test message'),
                MIMEText('This is a <em>test</em> message', 'html')])
        self._post_email(
            self.email_address,
            [self.forum.email_address],
            'Test Simple Thread',
            msg)
        r = self.app.get('/p/test/discussion/testforum/')
        assert 'Test Simple Thread' in str(r), r
        assert len(r.html.findAll('tr')) == 2
        href = r.html.findAll('tr')[1].find('a')['href']
        r = self.app.get(href)
        assert 'alternate' in str(r)

    def test_html_email_with_images(self):
        msg = MIMEMultipart(
            _subparts=[
                MIMEMultipart(
                    'alternative',
                    _subparts=[
                        MIMEText('This is a test message'),
                        MIMEText('This is a <em>test</em> message', 'html')
                    ])
            ])
        with open(pkg_resources.resource_filename(
                'forgediscussion', 'tests/data/python-logo.png'), 'rb') as fp:
            img = MIMEImage(fp.read())
            img.add_header('Content-Disposition', 'attachment',
                           filename='python-logo.png')
            msg.attach(img)
        self._post_email(
            self.email_address,
            [self.forum.email_address],
            'Test Simple Thread',
            msg)
        r = self.app.get('/p/test/discussion/testforum/')
        assert 'Test Simple Thread' in str(r)
        assert len(r.html.findAll('tr')) == 2
        href = r.html.findAll('tr')[1].find('a')['href']
        r = self.app.get(href)
        assert 'alternate' in str(r)
        assert 'python-logo.png' in str(r)

    def _post_email(self, mailfrom, rcpttos, subject, msg):
        '''msg is MIME message object'''
        msg['Message-ID'] = '<' + h.gen_message_id() + '>'
        msg['From'] = mailfrom
        msg['To'] = ', '.join(rcpttos)
        msg['Subject'] = subject
        mail_tasks.route_email(
            peer='127.0.0.1',
            mailfrom=mailfrom,
            rcpttos=rcpttos,
            data=msg.as_string())
        M.artifact_orm_session.flush()


class TestForumMessageHandling(TestController):
    '''
    Tests all the "handle_message" related logic, which is what inbound emails run through
    '''

    def setup_method(self, method):
        super().setup_method(method)
        self.app.get('/discussion/')
        r = self.app.get('/admin/discussion/forums')
        form = r.forms['add-forum']
        form['add_forum.shortname'] = 'testforum'
        form['add_forum.name'] = 'Test Forum'
        form.submit()
        r = self.app.get('/admin/discussion/forums')
        assert 'Test Forum' in r
        form = r.forms['add-forum']
        form['add_forum.shortname'] = 'test1'
        form['add_forum.name'] = 'Test Forum 1'
        form.submit()
        r = self.app.get('/admin/discussion/forums')
        assert 'Test Forum 1' in r
        h.set_context('test', 'discussion', neighborhood='Projects')
        self.user = M.User.query.get(username='root')

    def test_has_access(self):
        assert not c.app.has_access(M.User.anonymous(), 'testforum')
        assert c.app.has_access(M.User.query.get(username='root'), 'testforum')

    def test_post(self):
        self._post('testforum', 'Test Thread', 'Nothing here')

    def test_bad_post(self):
        self._post('Forumtest', 'Test Thread', 'Nothing here')

    def test_reply(self):
        self._post('testforum', 'Test Thread', 'Nothing here',
                   message_id='test_reply@domain.net')
        assert FM.ForumThread.query.find().count() == 1
        posts = FM.ForumPost.query.find()
        assert posts.count() == 1
        assert FM.ForumThread.query.get().num_replies == 1
        assert FM.ForumThread.query.get().first_post_id == 'test_reply@domain.net'

        post = posts.first()
        self._post('testforum', 'Test Reply', 'Nothing here, either',
                   message_id='test_reply-msg2@domain.net',
                   in_reply_to=['test_reply@domain.net'])
        assert FM.ForumThread.query.find().count() == 1
        assert FM.ForumPost.query.find().count() == 2
        assert FM.ForumThread.query.get().first_post_id == 'test_reply@domain.net'

    def test_reply_using_references_headers(self):
        self._post('testforum', 'Test Thread', 'Nothing here',
                   message_id='first-message-id')
        prev_post = FM.ForumPost.query.find().first()
        thread = FM.ForumThread.query.find().first()

        refs = M.Notification._references(thread, prev_post) + ['first-message-id']
        self._post('testforum', 'Test Thread', 'Nothing here, yet',
                   message_id='second-message-id',
                   in_reply_to=['some-other-id@not.helpful.com'],
                   references=refs)
        assert FM.ForumThread.query.find().count() == 1
        assert FM.ForumPost.query.find().count() == 2

        prev_post = FM.ForumPost.query.find().sort('timestamp', pymongo.DESCENDING).first()
        refs = M.Notification._references(thread, prev_post) + ['second-message-id']
        self._post('testforum', 'Test Reply', 'Nothing here, either',
                   message_id='third-message-id',
                   # missing in_reply_to altogether
                   references=refs)
        assert FM.ForumThread.query.find().count() == 1
        assert FM.ForumPost.query.find().count() == 3

    def test_attach(self):
        # runs handle_artifact_message() with filename field
        self._post('testforum', 'Attachment Thread', 'This is text attachment',
                   message_id='test.attach.100@domain.net',
                   filename='test.txt',
                   content_type='text/plain')
        # runs handle_artifact_message() where there's no post with given message_id yet
        self._post('testforum', 'Test Thread', b'Nothing here',
                   message_id='test.attach.100@domain.net')
        # runs handle_artifact_message() where there IS a post with given message_id
        self._post('testforum', 'Attachment Thread', 'This is binary ¶¬¡™£¢¢•º™™¶'.encode(),
                   message_id='test.attach.100@domain.net',
                   content_type='text/plain')

    def test_threads(self):
        self._post('testforum', 'Test', 'test')
        thd = FM.ForumThread.query.find().first()
        url = '/discussion/testforum/thread/%s/' % thd._id
        self.app.get(url)
        resp = self.app.get('/discussion/testforum/thread/foobar/', status=301)
        assert('/discussion/testforum/' in resp.location)

    def test_posts(self):
        # not sure why this fails when set to root (to match self.user_id)
        c.user = M.User.by_username('test-admin')
        self._post('testforum', 'Test', 'test')
        thd = FM.ForumThread.query.find().first()
        thd_url = '/discussion/testforum/thread/%s/' % thd._id
        r = self.app.get(thd_url)
        p = FM.ForumPost.query.find().first()
        url = str(f'/discussion/testforum/thread/{thd._id}/{p.slug}/')
        r = self.app.get(url)
        f = r.html.find('form', {'action': '/p/test' + url})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params['subject'] = 'New Subject'
        params['text'] = 'Asdf'
        r = self.app.post(url, params=params)
        assert 'Asdf' in self.app.get(url)
        r = self.app.get(url, params=dict(version='1'))
        post_form = r.html.find('form', {'action': '/p/test' + url + 'reply'})
        params = dict()
        inputs = post_form.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[post_form.find('textarea')['name']] = 'text'
        r = self.app.post(url + 'reply', params=params)
        self._post('testforum', 'Test Reply', 'Nothing here, either',
                   message_id='test_posts@domain.net',
                   in_reply_to=[p._id])
        reply = FM.ForumPost.query.get(_id='test_posts@domain.net')
        r = self.app.get(thd_url + reply.slug + '/')
        # Check attachments
        r = self.app.post(url + 'attach',
                          upload_files=[('file_info', 'test.txt', b'This is a textfile')])
        r = self.app.post(url + 'attach',
                          upload_files=[('file_info', 'test.asdfasdtxt',
                                         b'This is a textfile')])
        r = self.app.post(url + 'attach',
                          upload_files=[('file_info', 'test1.txt', b'This is a textfile'),
                                        ('file_info', 'test2.txt', b'This is a textfile')])
        r = self.app.get(url)
        assert "test1.txt" in r
        assert "test2.txt" in r
        for link in r.html.findAll('a.btn'):
            if 'attachment' in link.get('href', ''):
                self.app.get(str(link['href']))
                self.app.post(str(link['href']), params=dict(delete='on'))
        reply_slug = str(reply.slug)
        r = self.app.post(url + reply_slug + '/moderate',
                          params=dict(subject='', delete='on'))
        slug = reply_slug[:4]
        r = self.app.post(url + slug + '/moderate',
                          params=dict(subject='', delete='on'))

    def _post(self, topic, subject, body, **kw):
        '''
        Submit a message very similar to how incoming email works
        '''
        message_id = kw.pop('message_id', '%s@test.com' % random.random())
        with h.push_config(c, user=self.user):
            c.app.handle_message(
                topic,
                dict(kw,
                     project_id=c.project._id,
                     mount_point='discussion',
                     headers=dict(Subject=subject),
                     payload=body,
                     message_id=message_id))
        M.artifact_orm_session.flush()


class TestForum(TestController):
    def setup_method(self, method):
        super().setup_method(method)
        self.app.get('/discussion/')
        r = self.app.get('/admin/discussion/forums')
        form = r.forms['add-forum']
        form['add_forum.shortname'] = 'testforum'
        form['add_forum.name'] = 'Test Forum'
        form.submit()
        r = self.app.get('/admin/discussion/forums')
        frm = FM.Forum.query.get(shortname='testforum')
        assert 'testforum' in r
        h.set_context('test', 'discussion', neighborhood='Projects')
        frm = FM.Forum.query.get(shortname='testforum')
        r = self.app.get('/admin/discussion/forums')
        form = r.forms['add-forum']
        form['add_forum.shortname'] = 'childforum'
        form['add_forum.name'] = 'Child Forum'
        form['add_forum.parent'] = str(frm._id)
        form.submit()
        r = self.app.get('/admin/discussion/forums')
        assert 'childforum' in r

    @staticmethod
    def fill_thread_reply(r):
        form = r.forms['edit_post']
        for field in form.fields.values():
            field = field[0]
            if field.id is None:
                continue
            if 'text' in field.id:
                form[field.name] = 'Test_Reply'
        return form

    @staticmethod
    def fill_new_topic_form(r):
        form = r.forms['create_new_topic']
        for field in form.fields.values():
            field = field[0]
            if field.id is None:
                continue
            if 'subject' in field.id:
                form[field.name] = 'Test_Subject'
            if 'forum' in field.id:
                form[field.name] = 'testforum'
            if 'text' in field.id:
                form[field.name] = 'Test_Description'
        return form

    def test_unicode_name(self):
        r = self.app.get('/admin/discussion/forums')
        form = r.forms['add-forum']
        form['add_forum.shortname'] = 'téstforum'.encode()
        form['add_forum.name'] = 'Tést Forum'.encode()
        form.submit()
        r = self.app.get('/admin/discussion/forums')
        assert 'téstforum'.encode() in r

    def test_markdown_description(self):
        r = self.app.get('/admin/discussion/forums')
        form = r.forms['add-forum']
        form['add_forum.shortname'] = 'tester'
        form['add_forum.name'] = 'Tester'
        form['add_forum.description'] = '<a href="http://cnn.com">This is CNN</a>'
        form.submit()
        r = self.app.get('/discussion/')
        assert len(r.html.findAll('a', rel='nofollow')) == 2

    def test_forum_search(self):
        self.app.get('/discussion/search')
        self.app.get('/discussion/search', params=dict(q='foo'))

    def test_forum_index(self):
        self.app.get('/discussion/testforum/')
        self.app.get('/discussion/testforum/childforum/')

    def test_threads_with_zero_posts(self):
        # Make sure that threads with zero posts (b/c all posts have been
        # deleted or marked as spam) don't show in the UI.

        # FIXME: This only works for posts that were initially pending, not
        # those deleted or spammed later.

        self._set_anon_allowed()

        def _post_pending():
            r = self.app.get('/discussion/create_topic/')
            f = r.html.find(
                'form', {'action': '/p/test/discussion/save_new_topic'})
            params = dict()
            inputs = f.findAll('input')
            for field in inputs:
                if field.has_attr('name'):
                    params[field['name']] = field.get('value') or ''
            params[f.find('textarea')['name']] = '1st post in Zero Posts thread'
            params[f.find('select')['name']] = 'testforum'
            params[f.find('input', {'style': 'width: 90%'})['name']] = 'Test Zero Posts'
            r = self.app.post('/discussion/save_new_topic', params=params,
                              extra_environ=dict(username='*anonymous'),
                              status=302)
            assert r.location.startswith(
                'http://localhost/p/test/discussion/testforum/thread/'), r.location

        def _check():
            r = self.app.get('/discussion/')
            assert 'Test Zero Posts' not in r
            r = self.app.get('/discussion/testforum/')
            assert 'Test Zero Posts' not in r

        # test posts marked as spam
        _post_pending()
        r = self.app.get('/discussion/testforum/moderate?status=pending')
        post_id = r.html.find('input', {'name': 'post-0._id'})['value']
        r = self.app.post('/discussion/testforum/moderate/save_moderation', params={
            'post-0._id': post_id,
            'post-0.checked': 'on',
            'spam': 'Spam Marked'})
        _check()

        # test posts deleted
        _post_pending()
        r = self.app.get('/discussion/testforum/moderate?status=pending')
        post_id = r.html.find('input', {'name': 'post-0._id'})['value']
        r = self.app.post('/discussion/testforum/moderate/save_moderation', params={
            'post-0._id': post_id,
            'post-0.checked': 'on',
            'delete': 'Delete Marked'})
        _check()

    def test_user_filter(self):
        username = 'test_username1'
        r = self.app.get(
            '/discussion/testforum/moderate?username=%s' % username)
        input_field = r.html.find('input', {'value': username})
        assert input_field is not None

        username = None
        r = self.app.get(
            '/discussion/testforum/moderate?username=%s' % username)
        input_field = r.html.fieldset.find('input', {'value': username})
        assert input_field is None

    def test_save_moderation_bulk_user(self):
        # create posts
        for i in range(5):
            r = self.app.get('/discussion/create_topic/')
            f = r.html.find(
                'form', {'action': '/p/test/discussion/save_new_topic'})
            params = dict()
            inputs = f.findAll('input')
            for field in inputs:
                if field.has_attr('name'):
                    params[field['name']] = field.get('value') or ''
            params[f.find('textarea')['name']] = 'Post text'
            params[f.find('select')['name']] = 'testforum'
            params[f.find('input', {'style': 'width: 90%'})['name']] = "this is my post"
            r = self.app.post('/discussion/save_new_topic', params=params)

        assert 5 == FM.ForumPost.query.find({'status': 'ok'}).count()

        r = self.app.post('/discussion/testforum/moderate/save_moderation_bulk_user', params={
            'username': 'test-admin',
            'spam': '1'})
        assert '5 posts marked as spam' in self.webflash(r)
        assert 5 == FM.ForumPost.query.find({'status': 'spam'}).count()

    def test_posting(self):
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'This is a *test thread*'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = 'Test Thread'
        r = self.app.post('/discussion/save_new_topic', params=params)
        r = self.app.get('/admin/discussion/forums')
        assert 'Message posted' in r
        r = self.app.get('/discussion/testforum/moderate/')
        n = M.Notification.query.get(subject='[test:discussion] Test Thread')
        post = FM.ForumPost.query.get(text='This is a *test thread*')
        assert post.url_paginated() in n.text
        assert 'This is a *test thread*\n\n\n---\n\n[Test Thread]' in n.text
        assert '[Test Thread](' in n.text
        assert 'noreply' not in n.reply_to_address, n
        assert 'testforum@discussion.test.p' in n.reply_to_address, n

    def test_new_topic_rate_limit(self):
        with h.push_config(config, **{'forgediscussion.rate_limits_per_user': '{"3600": 1}'}):
            # first one should succeed
            self.test_posting()

            # second should fail
            with pytest.raises(Exception):
                self.test_posting()

    def test_notifications_escaping(self):
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find(
            'form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'Post text'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = "this is <h2> o'clock"
        r = self.app.post('/discussion/save_new_topic', params=params)
        n = M.Notification.query.find(
            dict(subject="[test:discussion] this is <h2> o'clock")).first()
        assert '---\n\n[this is &lt;h2&gt; o&#39;clock]' in n.text

    def _set_anon_allowed(self):
        r = self.app.get('/admin/discussion/permissions')
        select = r.html.find('select', {'name': 'card-3.new'})
        opt_anon = select.find(text='*anonymous').parent
        opt_auth = select.find(text='*authenticated').parent
        opt_admin = select.find(text='Admin').parent
        r = self.app.post('/admin/discussion/update', params={
            'card-0.id': 'admin',
            'card-0.value': opt_admin['value'],
            'card-4.id': 'read',
            'card-4.value': opt_anon['value'],
            'card-3.id': 'post',
            'card-3.value': opt_auth['value'],
            'card-3.new': opt_anon['value'],
        })

    @mock.patch('allura.model.discuss.g.spam_checker')
    def test_anonymous_post(self, spam_checker):
        spam_checker.check.return_value = False
        self._set_anon_allowed()
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'Post content'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = 'Test Thread'
        thread = self.app.post('/discussion/save_new_topic', params=params,
                               extra_environ=dict(username='*anonymous'))

        # assert post return 404 but content can still be seen and moderated
        thread_url = thread.response.headers['Location']
        r = self.app.get(thread_url, status=404,
                         extra_environ=dict(username='*anonymous'))
        assert 'Post awaiting moderation' in r
        assert 'name="delete"' not in r
        assert 'name="approve"' not in r
        assert 'name="spam"' not in r
        assert "Post content" not in r
        assert spam_checker.check.call_args[0][0] == 'Test Thread\nPost content'

        # assert unapproved thread replies do not appear
        f = r.html.find('div', {'class': 'comment-row reply_post_form'}).find('form')
        rep_url = f.get('action')
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'anon reply to anon post content'
        r = self.app.post(str(rep_url), params=params, extra_environ=dict(username='*anonymous'))
        r = self.app.get(thread_url, status=404,
                         extra_environ=dict(username='*anonymous'))
        assert 'anon reply to anon post' not in r
        assert spam_checker.check.call_args[0][0] == 'anon reply to anon post content'

        # assert moderation controls appear for admin
        r = self.app.get(thread_url, extra_environ=dict(username='test-admin'), status=404)
        assert '<div class="display_post moderate">' in r
        assert '<i class="fa fa-reply"></i>' in r

        assert 'name="delete"' in r
        assert 'name="approve"' in r
        assert 'name="spam"' in r
        assert 'Post content' in r

        # assert anon posts appear in moderation queue
        r = self.app.get('/discussion/testforum/moderate/')
        post = FM.ForumPost.query.get(text='Post content')
        post2 = FM.ForumPost.query.get(text='anon reply to anon post content')
        link = '<a href="{}">[{}]</a>'.format(post.thread.url() + '?limit=25#' + post.slug, post.shorthand_id())
        assert link in r, link
        link = '<a href="{}">[{}]</a>'.format(post2.thread.url() + '?limit=25#' + post2.slug, post2.shorthand_id())
        assert link in r, link

        # approve posts
        r = self.app.post('/discussion/testforum/moderate/save_moderation', params={
            'post-0._id': post._id,
            'post-0.checked': 'on',
            'approve': 'Approve Marked'})

        post = FM.ForumPost.query.get(text='Post content')
        post2 = FM.ForumPost.query.get(text='anon reply to anon post content')
        assert 'ok' == post.status
        assert 'pending' == post2.status

        # assert anon can't edit their original post
        r = self.app.get(thread_url,
                         extra_environ=dict(username='*anonymous'))
        assert 'Post content' in r
        post_container = r.html.find('div', {'id': post.slug})

        btn_edit = post_container.find('a', {'title': 'Edit'})
        assert not btn_edit



    @td.with_tool('test2', 'Discussion', 'discussion')
    @mock.patch('allura.model.discuss.g.spam_checker')
    def test_is_spam(self, spam_checker):
        spam_checker.check.return_value = True
        c.user = M.User.query.get(username="test-user")
        role = M.ProjectRole(project_id=c.project._id, name='TestRole')
        M.ProjectRole.by_user(c.user, upsert=True).roles.append(role._id)
        ThreadLocalORMSession.flush_all()
        t = M.Thread()
        p = M.Post(thread=t)
        assert 'TestRole' in [r.name for r in c.project.named_roles]
        assert not t.is_spam(p)

    def test_thread(self):
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find(
            'form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'aaa'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = 'AAA'
        thread = self.app.post('/discussion/save_new_topic', params=params).follow()
        url = thread.request.url

        # test reply to post
        f = thread.html.find('div', {'class': 'comment-row reply_post_form'}).find('form')
        rep_url = f.get('action')
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'bbb'
        thread = self.app.post(str(rep_url), params=params)
        thread = self.app.get(url)
        # beautiful soup is getting some unicode error here - test without it
        assert thread.html.findAll(
            'div', {'class': 'display_post'})[0].find('p').string == 'aaa'
        assert thread.html.findAll(
            'div', {'class': 'display_post'})[1].find('p').string == 'bbb'
        assert thread.response.text.count(
            '<div class="comment-row reply_post_form') == 2
        assert thread.response.text.count('<div class="edit_post_form') == 2

        # test edit post
        thread_url = thread.request.url
        r = thread
        reply_form = r.html.find('div', {'class': 'edit_post_form reply'}).find('form')
        post_link = str(reply_form['action'])
        params = dict()
        inputs = reply_form.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[reply_form.find('textarea')['name']] = 'zzz'
        self.app.post(post_link, params)
        r = self.app.get(thread_url)
        assert 'zzz' in r.html.find('div', {'class': 'display_post'}).text
        assert 'Last edit: Test Admin ' in r.html.find('div', {'class': 'display_post'}).text

    def test_subscription_controls(self):
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'Post text'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = 'Post subject'
        thread = self.app.post('/discussion/save_new_topic', params=params).follow()
        assert M.Notification.query.find(
            dict(subject='[test:discussion] Post subject')).count() == 1
        r = self.app.get('/discussion/testforum/')
        f = r.html.find('form', {'class': 'follow_form'})
        subscribe_url = f.get('action')
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        self.app.post(str(subscribe_url), params=params)
        self.app.post('/discussion/general/subscribe_to_forum', {'subscribe': 'True'})
        f = thread.html.find('div', {'class': 'comment-row reply_post_form'}).find('form')
        rep_url = f.get('action')
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'Reply 2'
        self.app.post(str(rep_url), params=params)
        assert M.Notification.query.find(
            dict(subject='[test:discussion] Re: Post subject')).count() == 1

    def get_table_rows(self, response, closest_id):
        tbody = response.html.find('div', {'id': closest_id}).find('tbody')
        rows = tbody.findAll('tr')
        return rows

    def check_announcement_table(self, response, topic_name):
        assert response.html.find(text='Announcements')
        rows = self.get_table_rows(response, 'announcements')
        assert len(rows) == 1
        cell = rows[0].findAll('td', {'class': 'topic'})
        assert topic_name in str(cell)

    def test_thread_announcement(self):
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'aaa aaa'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = 'AAAA'
        r = self.app.post('/discussion/save_new_topic', params=params).follow()
        url = r.request.url
        thread_id = url.rstrip('/').rsplit('/', 1)[-1]
        r = self.app.post(url + 'moderate', params=dict(
            flags='Announcement',
            discussion='testforum'))
        thread2 = FM.ForumThread.query.get(_id=thread_id)
        assert thread2.flags == ['Announcement']

        # Check that announcements are on front discussion page
        r = self.app.get('/discussion/')
        self.check_announcement_table(r, 'AAAA')
        # Check that announcements are on each forum's page
        r = self.app.get('/discussion/testforum/')
        self.check_announcement_table(r, 'AAAA')
        r = self.app.get('/discussion/testforum/childforum/')
        self.check_announcement_table(r, 'AAAA')

    def test_post_to_feed(self):
        # Create a new topic
        r = self.app.get('/discussion/create_topic/')
        form = self.fill_new_topic_form(r)
        thread = form.submit().follow()
        url = thread.request.url

        # Check that the newly created topic is the most recent in the rss feed
        f = self.app.get('/discussion/feed.rss').text
        f = feedparser.parse(f)
        newest_entry = f['entries'][0]['summary_detail']['value'].split("</p>")[0].split("<p>")[-1]
        assert newest_entry == 'Test_Description'

        # Reply to the newly created thread.
        thread = self.app.get(url)
        form = self.fill_thread_reply(thread)
        form.submit()

        # Check that reply matches the newest in the rss feed
        f = self.app.get('/discussion/feed.rss').text
        f = feedparser.parse(f)
        newest_reply = f['entries'][0]['summary_detail']['value'].split("</p>")[0].split("<p>")[-1]
        assert newest_reply == 'Test_Reply'

    def test_thread_sticky(self):
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'aaa aaa'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = 'topic1'
        r = self.app.post('/discussion/save_new_topic', params=params).follow()
        url1 = r.request.url
        tid1 = url1.rstrip('/').rsplit('/', 1)[-1]

        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'aaa aaa'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = 'topic2'
        r = self.app.post('/discussion/save_new_topic', params=params).follow()

        # Check that threads are ordered in reverse creation order
        r = self.app.get('/discussion/testforum/')
        rows = self.get_table_rows(r, 'forum_threads')
        assert len(rows) == 2
        assert 'topic2' in str(rows[0])
        assert 'topic1' in str(rows[1])

        # Make oldest thread Sticky
        r = self.app.post(url1 + 'moderate', params=dict(
            flags='Sticky',
            discussion='testforum'))
        thread1 = FM.ForumThread.query.get(_id=tid1)
        assert thread1.flags == ['Sticky']

        # Check that Sticky thread is at the top
        r = self.app.get('/discussion/testforum/')
        rows = self.get_table_rows(r, 'forum_threads')
        assert len(rows) == 2
        assert 'topic1' in rows[0].text
        assert 'topic2' in rows[1].text

        # Reset Sticky flag
        r = self.app.post(url1 + 'moderate', params=dict(
            flags='',
            discussion='testforum'))
        thread1 = FM.ForumThread.query.get(_id=tid1)
        assert thread1.flags == []

        # Would check that threads are again in reverse creation order,
        # but so far we actually sort by mod_date, and resetting a flag
        # updates it
        r = self.app.get('/discussion/testforum/')
        rows = self.get_table_rows(r, 'forum_threads')
        assert len(rows) == 2
        # assert 'topic2' in str(rows[0])
        # assert 'topic1' in str(rows[1])

    def test_move_thread(self):
        # make the topic
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'aaa aaa'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = 'topic1'
        thread = self.app.post(
            '/discussion/save_new_topic', params=params).follow()
        url = thread.request.url
        # make a reply
        f = thread.html.find(
            'div', {'class': 'comment-row reply_post_form'}).find('form')
        rep_url = f.get('action')
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'bbb'
        thread = self.app.post(str(rep_url), params=params)
        thread = self.app.get(url)
        # make sure the posts are in the original thread
        posts = thread.html.find('div', {'id': 'comment'}).findAll(
            'div', {'class': 'discussion-post'})
        assert len(posts) == 2
        # move the thread
        r = self.app.post(url + 'moderate', params=dict(
            flags='',
            discussion='general')).follow()
        # make sure all the posts got moved
        posts = r.html.find('div', {'id': 'comment'}).findAll(
            'div', {'class': 'discussion-post'})
        assert len(posts) == 2

    def test_rename_thread(self):
        # make the topic
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'aaa aaa'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = 'first subject'

        resp = self.app.post(
            '/discussion/save_new_topic', params=params).follow()
        url = resp.request.url
        resp = self.app.get(url)

        assert 'first subject' in resp

        f = resp.html.find('div', {'id':'mod_thread_form'}).find('form')
        params=dict(
            flags='',
            discussion='general',
            subject='changed subject')
        resp = self.app.post(str(f.get('action')), params=params).follow()
        resp = self.app.get(url)

        assert 'first subject' not in resp.html
        assert 'changed subject' in resp

    def test_sidebar_menu(self):
        r = self.app.get('/discussion/')
        sidebar = r.html.find('div', {'id': 'sidebar'})
        sidebar_menu = str(sidebar)
        sidebar_links = [i['href'] for i in sidebar.findAll('a')]
        assert "/p/test/discussion/create_topic/" in sidebar_links
        assert "/p/test/discussion/new_forum" in sidebar_links
        assert '<h3 class="">Help</h3>' in sidebar_menu
        assert "/nf/markdown_syntax" in sidebar_links
        assert "flag_as_spam" not in sidebar_links
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'aaa'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = 'AAA'
        thread = self.app.post('/discussion/save_new_topic', params=params).follow()
        thread_sidebarmenu = str(thread.html.find('div', {'id': 'sidebar'}))
        assert "flag_as_spam" in thread_sidebarmenu

    def test_sidebar_menu_anon(self):
        r = self.app.get('/discussion/')
        sidebar = r.html.find('div', {'id': 'sidebar'})
        sidebar_menu = str(sidebar)
        sidebar_links = [i['href'] for i in sidebar.findAll('a')]
        assert "/p/test/discussion/create_topic/" in sidebar_links
        assert "/p/test/discussion/new_forum" in sidebar_links
        assert '<h3 class="">Help</h3>' in sidebar_menu
        assert "/nf/markdown_syntax" in sidebar_links
        assert "flag_as_spam" not in sidebar_menu
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'aaa'
        params[f.find('select')['name']] = 'testforum'
        params[f.find('input', {'style': 'width: 90%'})['name']] = 'AAA'
        thread = self.app.post('/discussion/save_new_topic',
                               params=params).follow(extra_environ=dict(username='*anonymous'))
        thread_sidebar_menu = str(thread.html.find('div', {'id': 'sidebar'}))
        assert "flag_as_spam" not in thread_sidebar_menu

    def test_feed(self):
        for ext in ['', '.rss', '.atom']:
            self.app.get('/discussion/feed%s' % ext, status=200)
            self.app.get('/discussion/general/feed%s' % ext, status=200)

    def test_create_topic(self):
        r = self.app.get('/p/test/discussion/create_topic/')
        assert 'Test Forum' in r
        assert 'General Discussion' in r
        r = self.app.get('/p/test/discussion/create_topic/general/')
        assert '<option value="general" selected>General Discussion</option>' in r
        r = self.app.get('/p/test/discussion/create_topic/testforum/')
        assert '<option value="testforum" selected>Test Forum</option>' in r

    def test_create_topic_unicode(self):
        r = self.app.get('/admin/discussion/forums')
        form = r.forms['add-forum']
        form['add_forum.shortname'] = 'téstforum'.encode()
        form['add_forum.name'] = 'Tést Forum'.encode()
        form.submit()
        r = self.app.get('/admin/discussion/forums')
        assert 'téstforum'.encode() in r
        r = self.app.get(h.urlquote('/p/test/discussion/create_topic/téstforum/'))
        assert '<option value="téstforum" selected>Tést Forum</option>' in r

    def test_create_topic_attachment(self):
        r = self.app.get('/discussion/create_topic/')
        form = self.fill_new_topic_form(r)
        for field in form.fields.values():
            field = field[0]
            if field.id is None:
                continue
            if 'attachment' in field.id:
                form[field.name] = ('myfile.txt', b'foo bar baz')  # webtest.Upload dooesn't work here
        r = form.submit().follow()
        assert 'myfile.txt' in r, r

    def test_viewing_a_thread_does_not_update_project_last_updated(self):
        # Create new topic/thread
        r = self.app.get('/discussion/create_topic/')
        url = self.fill_new_topic_form(r).submit().follow().request.url

        # Remember project's last_updated
        timestamp_before = M.Project.query.get(shortname='test').last_updated

        # View the thread and make sure project last_updated is not updated
        self.app.get(url)
        timestamp_after = M.Project.query.get(shortname='test').last_updated
        assert timestamp_before == timestamp_after


class TestForumStats(TestController):
    def test_stats(self):
        self.app.get('/discussion/stats', status=200)

    # mim doesn't support aggregate
    @mock.patch('ming.session.Session.aggregate')
    def test_stats_data(self, aggregate):
        # partial data, some days are implicit 0
        aggregate.return_value = iter([
            {
                "_id": {
                    "year": 2013,
                    "month": 1,
                    "day": 2},
                "posts": 3
            },
            {
                "_id": {
                    "year": 2013,
                    "month": 1,
                    "day": 3},
                "posts": 5
            },
            {
                "_id": {
                    "year": 2013,
                    "month": 1,
                    "day": 5},
                "posts": 2
            },
        ])
        r = self.app.get(
            '/discussion/stats_data?begin=2013-01-01&end=2013-01-06')
        assert r.json == {
            'begin': '2013-01-01 00:00:00',
            'end': '2013-01-06 00:00:00',
            'data': [
                [1356998400000, 0],
                [1357084800000, 3],
                [1357171200000, 5],
                [1357257600000, 0],
                [1357344000000, 2],
                [1357430400000, 0],
            ]
        }
