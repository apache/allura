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

import os
from mock import patch
import pytest
from webtest.app import AppError
from ming.odm import session

from allura.tests import TestController
from allura import model as M
from allura.lib import helpers as h
from tg import config


class TestDiscussBase(TestController):

    def _thread_link(self):
        home = self.app.get('/wiki/Home/')
        new_post = home.html.find('div', {'id': 'new_post_holder'})
        thread_link = new_post.find('form', {'id': 'edit_post'}).get('action')
        return thread_link.rstrip('post')

    def _thread_id(self):
        home = self.app.get('/wiki/Home/')
        new_post = home.html.find('div', {'id': 'new_post_holder'})
        thread_link = new_post.find('form', {'id': 'edit_post'}).get('action')
        return thread_link.split('/')[-2]


class TestDiscuss(TestDiscussBase):

    def _is_subscribed(self, user, thread):
        return M.Mailbox.query.get(user_id=user._id, artifact_index_id=thread.index_id())

    def test_subscribe_unsubscribe(self):
        user = M.User.by_username('test-admin')
        thread_id = self._thread_id()
        thread = M.Thread.query.get(_id=thread_id)

        # remove tool-wide subscription, so it doesn't interfere
        M.Mailbox.query.remove(dict(user_id=user._id, app_config_id=thread.app_config_id))

        assert not self._is_subscribed(user, thread)
        link = self._thread_link()
        params = {
            'threads-0._id': thread_id,
            'threads-0.subscription': 'on'}
        r = self.app.post('/wiki/_discuss/subscribe', params=params)
        assert self._is_subscribed(user, thread)
        params = {'threads-0._id': thread_id}
        r = self.app.post('/wiki/_discuss/subscribe', params=params)
        assert not self._is_subscribed(user, thread)

    def _make_post(self, text):
        thread_link = self._thread_link()
        thread = self.app.get(thread_link, expect_errors=True)
        for f in thread.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = text
        r = self.app.post(f['action'], params=params,
                          headers={'Referer': str(thread_link)},
                          status=302,
                          extra_environ=dict(username='root'))
        return self.app.get(r.response.headers['Location'], expect_errors=True)

    @patch('allura.controllers.discuss.g.spam_checker.check')
    @patch('allura.controllers.discuss.g.spam_checker.submit_spam')
    def test_post(self, submit_spam, check_spam):
        thread_link = self._thread_link()
        r = self._make_post('This is a post')
        assert 'This is a post' in r, r
        assert check_spam.call_args[0][0] == 'This is a post'

        post_link = str(
            r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])
        r = self.app.get(post_link[:-2], status=302)
        r = self.app.get(post_link)
        post_form = r.html.find('form', {'action': post_link})
        params = dict()
        inputs = post_form.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[post_form.find('textarea')['name']] = 'This is a new post'
        r = self.app.post(post_link,
                          params=params,
                          headers={'Referer': str(thread_link)})
        r = self.app.get(r.response.headers['Location'], status=404)
        assert 'This is a new post' in r, r
        r = self.app.get(post_link)
        assert str(r).count('This is a new post') == 3
        post_form = r.html.find('form', {'action': post_link + 'reply'})
        params = dict()
        inputs = post_form.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[post_form.find('textarea')['name']] = 'Tis a reply'
        r = self.app.post(post_link + 'reply',
                          params=params,
                          headers={'Referer': str(post_link)})
        r = self.app.get(thread_link)
        assert 'Tis a reply' in r, r
        permalinks = [post.find('form')['action']
                      for post in r.html.findAll('div', {'class': 'edit_post_form reply'})]
        self.app.post(permalinks[1] + 'flag')
        self.app.post(permalinks[1] + 'moderate', params=dict(delete='delete'))
        self.app.post(permalinks[0] + 'moderate', params=dict(spam='spam'))
        assert submit_spam.call_args[0] == (
            'This is a new post',), submit_spam.call_args[0]

    def test_rate_limit_comments(self):
        with h.push_config(config, **{'allura.rate_limits_per_user': '{"3600": 2}'}):
            for i in range(0, 2):
                r = self._make_post(f'This is a post {i}')
                assert 'rate limit exceeded' not in r.text

            r = self._make_post('This is a post that should fail.')
            assert 'rate limit exceeded' in r.text

    def test_permissions(self):
        thread_url = self._thread_link()
        thread_id = thread_url.rstrip('/').split('/')[-1]
        thread = M.Thread.query.get(_id=thread_id)

        # ok initially
        non_admin = 'test-user'
        self.app.get(thread_url, status=404,
                     extra_environ=dict(username=str(non_admin)))

        # set wiki page private
        from forgewiki.model import Page
        # need to look up the page directly, so ming is aware of our change
        page = Page.query.get(_id=thread.ref.artifact._id)
        project = M.Project.query.get(shortname='test')
        role_admin = M.ProjectRole.by_name('Admin', project)._id
        page.acl = [
            M.ACE.allow(role_admin, M.ALL_PERMISSIONS),
            M.DENY_ALL,
        ]

        self.app.get(thread_url, status=404,
                     extra_environ=dict(username='test-admin'))
        self.app.get(thread_url, status=403,  # forbidden
                     extra_environ=dict(username=str(non_admin)))

    def test_spam_link(self):
        r = self._make_post('Test post')
        assert '<span><i class="fa fa-exclamation" aria-hidden="true"></i></span>' in r
        r = self.app.get('/wiki/Home/', extra_environ={'username': 'test-user-1'})
        assert '<span><i class="fa fa-exclamation" aria-hidden="true"></i></span>' not in r, 'User without moderate perm must not see Spam link'

    @patch('allura.controllers.discuss.g.spam_checker.submit_spam')
    def test_moderate(self, submit_spam):
        r = self._make_post('Test post')
        post_link = str(
            r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])
        post = M.Post.query.find().first()
        post.status = 'pending'
        self.app.post(post_link + 'moderate', params=dict(spam='spam'))
        assert submit_spam.call_args[0] == (
            'Test post',), submit_spam.call_args[0]
        post = M.Post.query.find().first()
        assert post.status == 'spam'
        self.app.post(post_link + 'moderate', params=dict(approve='approve'))
        post = M.Post.query.find().first()
        assert post.status == 'ok'
        self.app.post(post_link + 'moderate', params=dict(delete='delete'))
        assert M.Post.query.find().count() == 1
        assert M.Post.query.find({'deleted': False}).count() == 0

    def test_comment_get_markdown(self):
        r = self._make_post('This is a post')
        post_id = str(
            r.html.find('div', {'class': 'discussion-post'})['id'])
        response = self.app.get(self._thread_link() + post_id + '/get_markdown')
        assert 'This is a post' in response

    def test_comment_update_markdown(self):
        r = self._make_post('This is a post')
        post_id = str(
            r.html.find('div', {'class': 'discussion-post'})['id'])
        update_link = str(self._thread_link() + post_id + '/update_markdown')
        response = self.app.post(
            update_link,
            params={
                'text': '- [x] checkbox'})
        assert response.json['status'] == 'success'
        # anon users can't edit markdown
        response = self.app.post(
            update_link,
            params={
                'text': '- [x] checkbox'},
            extra_environ=dict(username='*anonymous'))
        assert response.json['status'] == 'no_permission'

    def test_comment_post_reaction_new(self):
        r = self._make_post('This is a post')
        post_id = str(
            r.html.find('div', {'class': 'discussion-post'})['id'])
        react_link = str(self._thread_link() + post_id + '/post_reaction')
        response = self.app.post(
            react_link,
            params={
                'r': ':+1:'})
        assert response.json['status'] == 'ok'
        assert response.json['counts'][':+1:'] == 1
        response = self.app.post(
            react_link,
            params={
                'r': 'invalid'})
        assert response.json['status'] == 'error'
        assert response.json['counts'][':+1:'] == 1
        # anon users can't react comments
        response = self.app.post(
            react_link,
            params={
                'r': ':+1:'},
            extra_environ=dict(username='*anonymous'))
        assert response.json['error'] == 'no_permission'
        # even anon can't send invalid reactions
        response = self.app.post(
            react_link,
            params={
                'r': 'invalid'},
            extra_environ=dict(username='*anonymous'))
        assert response.json['error'] == 'no_permission'

    def test_comment_post_reaction_change(self):
        r = self._make_post('This is a post')
        post_id = str(
            r.html.find('div', {'class': 'discussion-post'})['id'])
        react_link = str(self._thread_link() + post_id + '/post_reaction')
        response = self.app.post(
            react_link,
            params={
                'r': ':-1:'})
        assert response.json['status'] == 'ok'
        assert response.json['counts'][':-1:'] == 1
        response = self.app.post(
            react_link,
            params={
                'r': ':+1:'})
        assert response.json['status'] == 'ok'
        assert response.json['counts'][':+1:'] == 1
        assert ':-1:' not in response.json['counts']

    def test_comment_post_reaction_undo(self):
        r = self._make_post('This is a post')
        post_id = str(
            r.html.find('div', {'class': 'discussion-post'})['id'])
        react_link = str(self._thread_link() + post_id + '/post_reaction')
        response = self.app.post(
            react_link,
            params={
                'r': ':tada:'})
        assert response.json['status'] == 'ok'
        assert response.json['counts'][':tada:'] == 1
        response = self.app.post(
            react_link,
            params={
                'r': ':tada:'})
        assert response.json['status'] == 'ok'
        assert ':tada:' not in response.json['counts']

    def test_user_filter(self):
        r = self._make_post('Test post')
        post_link = str(
            r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])
        r = self.app.post(post_link + 'moderate', params=dict(spam='spam'))
        assert r.json == {"result": "success"}
        post = M.Post.query.find().first()
        post_username = post.author().username
        moderate_link = '/p/test/wiki/_discuss/moderate'

        # no filter
        r_no_filtered = self.app.get(
            moderate_link,
            params=dict(
                status=post.status
            ))
        assert r_no_filtered.html.tbody.findAll('tr') != []

        # filter with existing user
        r_filtered = self.app.get(
            moderate_link,
            params=dict(
                username=post_username,
                status=post.status
            ))
        assert r_filtered.html.tbody.findAll('tr') != []
        assert post_username in r_filtered.html.tbody.findAll('td')[-5].string

        # filter without existing user
        r_bad_filtered = self.app.get(
            moderate_link,
            params=dict(
                username='bad_filtered_user',
                status=post.status
            ))
        assert r_bad_filtered.html.tbody.findAll('tr') == []

    def test_undo(self):
        r = self._make_post('Test post')
        post_link = str(
            r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])

        self.app.post(post_link + 'moderate', params=dict(
            undo='undo', prev_status='pending'))
        post = M.Post.query.find().first()
        assert post.status == 'pending'

        self.app.post(post_link + 'moderate', params=dict(
            undo='undo', prev_status='ok'))
        post = M.Post.query.find().first()
        assert post.status == 'ok'

    @patch.object(M.Thread, 'is_spam')
    def test_feed_does_not_include_comments_held_for_moderation(self, is_spam):
        is_spam.return_value = True
        r = self._make_post('Post needs moderation!')
        post_link = str(
            r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])
        post = M.Post.query.find().first()
        assert post.status == 'pending'
        r = self.app.get('/wiki/feed.rss')
        assert 'Post needs moderation!' not in r

        self.app.post(post_link + 'moderate', params=dict(approve='approve'))
        post = M.Post.query.find().first()
        assert post.status == 'ok'
        r = self.app.get('/wiki/feed.rss')
        assert 'Post needs moderation!' in r

    def test_post_paging(self):
        thread_link = self._thread_link()
        # just make sure it doesn't 500
        self.app.get('%s?limit=50&page=0' % thread_link, status=404)

    @patch('allura.controllers.discuss.g.director.create_activity')
    def test_edit_post(self, create_activity):
        r = self._make_post('This is a post')
        assert create_activity.call_count == 1, create_activity.call_count
        assert create_activity.call_args[0][1] == 'posted'
        create_activity.reset_mock()
        thread_url = r.request.url
        reply_form = r.html.find(
            'div', {'class': 'edit_post_form reply'}).find('form')
        post_link = str(reply_form['action'])
        assert 'This is a post' in r.html.find('div', {'class': 'display_post'}).text
        assert 'Last edit:' not in r.html.find('div', {'class': 'display_post'}).text
        params = dict()
        inputs = reply_form.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[reply_form.find('textarea')['name']] = 'zzz'
        self.app.post(post_link, params)
        assert create_activity.call_count == 1, create_activity.call_count
        assert create_activity.call_args[0][1] == 'modified'
        r = self.app.get(thread_url)
        assert 'zzz' in r.html.find('div', {'class': 'display_post'}).text
        assert 'Last edit: Test Admin ' in r.html.find('div', {'class': 'display_post'}).text

    def test_deleted_post(self):
        r = self._make_post('This is a post')
        reply_form = r.html.find(
            'div', {'class': 'edit_post_form reply'}).find('form')
        post_link = str(reply_form['action']).rstrip('/')
        _, slug = post_link.rsplit('/', 1)
        r = self.app.get(post_link, status=200)
        post = M.Post.query.get(slug=slug)
        post.deleted = True
        session(post).flush(post)
        r = self.app.get(post_link, status=404)


class TestAttachment(TestDiscussBase):

    def setup_method(self, method):
        super().setup_method(method)
        self.thread_link = self._thread_link()
        thread = self.app.get(self.thread_link, status=404)
        for f in thread.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        self.post_form_link = f['action']
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'Test Post'
        r = self.app.post(f['action'], params=params,
                          headers={'Referer': str(self.thread_link)})
        r = r.follow()
        self.post_link = str(
            r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])

    def attach_link(self):
        r = self.app.get(self.thread_link)
        for alink in r.html.findAll('a'):
            if 'attachment' in alink['href']:
                alink = str(alink['href'])
                return alink
        else:
            assert False, 'attachment link not found'

    def test_attach(self):
        r = self.app.post(self.post_link + 'attach',
                          upload_files=[('file_info', 'test.txt', b'HiThere!')])
        r = self.app.get(self.thread_link)
        assert '<div class="attachment_holder">' in r
        alink = self.attach_link()
        r = self.app.get(alink)
        assert r.content_type == 'text/plain'
        assert r.content_disposition == 'attachment;filename="test.txt"', 'Attachments should force download'
        r = self.app.post(self.post_link + 'attach',
                          upload_files=[('file_info', 'test.o12', b'HiThere!')])
        r = self.app.post(alink, params=dict(delete='on'))

    def test_attach_svg(self):
        r = self.app.post(self.post_link + 'attach',
                          upload_files=[('file_info', 'test.svg', b'<svg onclick="prompt(document.domain)"></svg>')])
        alink = self.attach_link()
        r = self.app.get(alink)
        assert r.content_type == 'image/svg+xml'
        assert r.content_disposition == 'attachment;filename="test.svg"', 'Attachments should force download'

    def test_attach_img(self):
        r = self.app.post(self.post_link + 'attach',
                          upload_files=[('file_info', 'handtinyblack.gif',
                                         b'GIF89a\x01\x00\x01\x00\x00\xff\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00;')])
        alink = self.attach_link()
        r = self.app.get(alink)
        assert r.content_type == 'image/gif'
        assert r.content_disposition is None

    @patch('allura.model.discuss.Post.notify')
    def test_reply_attach(self, notify):
        notify.return_value = True
        r = self.app.get(self.thread_link)
        post_form = r.html.find('form', {'action': self.post_link + 'reply'})
        params = dict()
        inputs = post_form.findAll('input')

        for field in inputs:
            if field.has_attr('name') and field['name'] != 'file_info':
                params[field['name']] = field.get('value') or ''
        params[post_form.find('textarea')['name']] = 'Reply'
        r = self.app.post(self.post_link + 'reply',
                          params=params,
                          upload_files=[('file_info', 'test.txt', b'HiThere!'),
                                        ('file_info', 'test2.txt', b'HiAgain!')])
        r = self.app.get(self.thread_link)
        assert "test.txt" in r

    def test_deleted_post_attachment(self):
        f = os.path.join(os.path.dirname(__file__), '..', 'data', 'user.png')
        with open(f, 'rb') as f:
            pic = f.read()
        self.app.post(
            self.post_link + 'attach',
            upload_files=[('file_info', 'user.png', pic)])
        alink = self.attach_link()
        thumblink = alink + '/thumb'
        self.app.get(alink, status=200)
        self.app.get(thumblink, status=200)
        _, slug = self.post_link.rstrip('/').rsplit('/', 1)
        post = M.Post.query.get(slug=slug)
        assert post, f'Could not find post for {slug} {self.post_link}'
        post.deleted = True
        session(post).flush(post)
        self.app.get(alink, status=404)
        self.app.get(thumblink, status=404)

    def test_unmoderated_post_attachments(self):
        ordinary_user = {'username': 'test-user'}
        moderator = {'username': 'test-admin'}
        # set up attachment
        f = os.path.join(os.path.dirname(__file__), '..', 'data', 'user.png')
        with open(f, 'rb') as f:
            pic = f.read()
        self.app.post(
            self.post_link + 'attach',
            upload_files=[('file_info', 'user.png', pic)])
        # ... make sure ordinary user can see it
        r = self.app.get(self.thread_link, extra_environ=ordinary_user)
        assert '<div class="attachment_holder">' in r
        alink = self.attach_link()
        thumblink = alink + '/thumb'
        # ... and access it
        self.app.get(alink, status=200, extra_environ=ordinary_user)
        self.app.get(thumblink, status=200, extra_environ=ordinary_user)

        # make post unmoderated
        _, slug = self.post_link.rstrip('/').rsplit('/', 1)
        post = M.Post.query.get(slug=slug)
        assert post, f'Could not find post for {slug} {self.post_link}'
        post.status = 'pending'
        session(post).flush(post)
        # ... make sure attachment is not visible to ordinary user
        r = self.app.get(self.thread_link, status=404, extra_environ=ordinary_user)
        assert '<div class="attachment_holder">' not in r, 'Attachment is visible on unmoderated post'
        # ... but visible to moderator
        r = self.app.get(self.thread_link, status=404, extra_environ=moderator)
        assert '<div class="attachment_holder">' in r
        # ... and ordinary user can't access it
        self.app.get(alink, status=403, extra_environ=ordinary_user)
        self.app.get(thumblink, status=403, extra_environ=ordinary_user)
        # ... but moderator can
        self.app.get(alink, status=200, extra_environ=moderator)
        self.app.get(thumblink, status=200, extra_environ=moderator)



