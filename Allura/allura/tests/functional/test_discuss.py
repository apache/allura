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
from nose.tools import assert_in, assert_not_in, assert_equal, assert_false, assert_true

from ming.odm import session

from allura.tests import TestController
from allura import model as M

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

    def _is_subscribed(self, username, thread_id):
        user_id = str(M.User.by_username(username)._id)
        thread = M.Thread.query.get(_id=thread_id)
        return thread.subscriptions.get(user_id)

    def test_subscribe_unsubscribe(self):
        user = 'test-admin'
        thread_id = self._thread_id()
        assert_false(self._is_subscribed(user, thread_id))
        link = self._thread_link()
        params = {
            'threads-0._id': thread_id,
            'threads-0.subscription': 'on'}
        r = self.app.post('/wiki/_discuss/subscribe', params=params)
        assert_true(self._is_subscribed(user, thread_id))
        params = {'threads-0._id': thread_id}
        r = self.app.post('/wiki/_discuss/subscribe', params=params)
        assert_false(self._is_subscribed(user, thread_id))

    def _make_post(self, text):
        thread_link = self._thread_link()
        thread = self.app.get(thread_link)
        for f in thread.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_key('name'):  # nopep8 - beautifulsoup3 actually uses has_key
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = text
        r = self.app.post(f['action'].encode('utf-8'), params=params,
                          headers={'Referer': thread_link.encode("utf-8")},
                          extra_environ=dict(username='root'))
        r = r.follow()
        return r

    @patch('allura.controllers.discuss.g.spam_checker.submit_spam')
    def test_post(self, submit_spam):
        thread_link = self._thread_link()
        r = self._make_post('This is a post')
        assert 'This is a post' in r, r
        post_link = str(
            r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])
        r = self.app.get(post_link[:-2], status=302)
        r = self.app.get(post_link)
        post_form = r.html.find('form', {'action': post_link})
        params = dict()
        inputs = post_form.findAll('input')
        for field in inputs:
            if field.has_key('name'):  # nopep8 - beautifulsoup3 actually uses has_key
                params[field['name']] = field.get('value') or ''
        params[post_form.find('textarea')['name']] = 'This is a new post'
        r = self.app.post(post_link,
                          params=params,
                          headers={'Referer': thread_link.encode("utf-8")})
        r = r.follow()
        assert 'This is a new post' in r, r
        r = self.app.get(post_link)
        assert str(r).count('This is a new post') == 3
        post_form = r.html.find('form', {'action': post_link + 'reply'})
        params = dict()
        inputs = post_form.findAll('input')
        for field in inputs:
            if field.has_key('name'):  # nopep8 - beautifulsoup3 actually uses has_key
                params[field['name']] = field.get('value') or ''
        params[post_form.find('textarea')['name']] = 'Tis a reply'
        r = self.app.post(post_link + 'reply',
                          params=params,
                          headers={'Referer': post_link.encode("utf-8")})
        r = self.app.get(thread_link)
        assert 'Tis a reply' in r, r
        permalinks = [post.find('form')['action'].encode('utf-8')
                      for post in r.html.findAll('div', {'class': 'edit_post_form reply'})]
        self.app.post(permalinks[1] + 'flag')
        self.app.post(permalinks[1] + 'moderate', params=dict(delete='delete'))
        self.app.post(permalinks[0] + 'moderate', params=dict(spam='spam'))
        assert submit_spam.call_args[0] == (
            'This is a new post',), submit_spam.call_args[0]

    def test_permissions(self):
        thread_url = self._thread_link()
        thread_id = thread_url.rstrip('/').split('/')[-1]
        thread = M.Thread.query.get(_id=thread_id)

        # ok initially
        non_admin = 'test-user'
        self.app.get(thread_url, status=200,
                     extra_environ=dict(username=non_admin))

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

        self.app.get(thread_url, status=200,  # ok
                     extra_environ=dict(username='test-admin'))
        self.app.get(thread_url, status=403,  # forbidden
                     extra_environ=dict(username=non_admin))

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

    def test_user_filter(self):
        r = self._make_post('Test post')
        post_link = str(
            r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])
        self.app.post(post_link + 'moderate', params=dict(spam='spam'))
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
        assert_equal(post.status, 'pending')
        r = self.app.get('/wiki/feed.rss')
        assert_not_in('Post needs moderation!', r)

        self.app.post(post_link + 'moderate', params=dict(approve='approve'))
        post = M.Post.query.find().first()
        assert_equal(post.status, 'ok')
        r = self.app.get('/wiki/feed.rss')
        assert_in('Post needs moderation!', r)

    def test_post_paging(self):
        thread_link = self._thread_link()
        # just make sure it doesn't 500
        self.app.get('%s?limit=50&page=0' % thread_link)

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
        assert 'This is a post' in str(
            r.html.find('div', {'class': 'display_post'}))
        assert 'Last edit:' not in str(
            r.html.find('div', {'class': 'display_post'}))
        params = dict()
        inputs = reply_form.findAll('input')
        for field in inputs:
            if field.has_key('name'):  # nopep8 - beautifulsoup3 actually uses has_key
                params[field['name']] = field.get('value') or ''
        params[reply_form.find('textarea')['name']] = 'zzz'
        self.app.post(post_link, params)
        assert create_activity.call_count == 1, create_activity.call_count
        assert create_activity.call_args[0][1] == 'modified'
        r = self.app.get(thread_url)
        assert 'zzz' in str(r.html.find('div', {'class': 'display_post'}))
        assert 'Last edit: Test Admin less than 1 minute ago' in str(
            r.html.find('div', {'class': 'display_post'}))

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

    def setUp(self):
        super(TestAttachment, self).setUp()
        self.thread_link = self._thread_link()
        thread = self.app.get(self.thread_link)
        for f in thread.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        self.post_form_link = f['action'].encode('utf-8')
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_key('name'):  # nopep8 - beautifulsoup3 actually uses has_key
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'Test Post'
        r = self.app.post(f['action'].encode('utf-8'), params=params,
                          headers={'Referer': self.thread_link.encode('utf-8')})
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
                          upload_files=[('file_info', 'test.txt', 'HiThere!')])
        r = self.app.get(self.thread_link)
        assert '<div class="attachment_thumb">' in r
        alink = self.attach_link()
        r = self.app.get(alink)
        assert r.content_type == 'text/plain'
        assert r.content_disposition == 'attachment;filename="test.txt"', 'Attachments should force download'
        r = self.app.post(self.post_link + 'attach',
                          upload_files=[('file_info', 'test.o12', 'HiThere!')])
        r = self.app.post(alink, params=dict(delete='on'))

    def test_attach_svg(self):
        r = self.app.post(self.post_link + 'attach',
                          upload_files=[('file_info', 'test.svg', '<svg onclick="prompt(document.domain)"></svg>')])
        alink = self.attach_link()
        r = self.app.get(alink)
        assert r.content_type == 'image/svg+xml'
        assert r.content_disposition == 'attachment;filename="test.svg"', 'Attachments should force download'

    def test_attach_img(self):
        r = self.app.post(self.post_link + 'attach',
                          upload_files=[('file_info', 'handtinyblack.gif',
                                         'GIF89a\x01\x00\x01\x00\x00\xff\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00;')])
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
            if field.has_key('name') and field['name'] != 'file_info':  # nopep8 - beautifulsoup3 actually uses has_key
                params[field['name']] = field.get('value') or ''
        params[post_form.find('textarea')['name']] = 'Reply'
        r = self.app.post(self.post_link + 'reply',
                          params=params,
                          upload_files=[('file_info', 'test.txt', 'HiThere!')])
        r = self.app.get(self.thread_link)
        assert "test.txt" in r

    def test_deleted_post_attachment(self):
        f = os.path.join(os.path.dirname(__file__), '..', 'data', 'user.png')
        with open(f) as f:
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
        assert post, 'Could not find post for {} {}'.format(slug, self.post_link)
        post.deleted = True
        session(post).flush(post)
        self.app.get(alink, status=404)
        self.app.get(thumblink, status=404)

    def test_unmoderated_post_attachments(self):
        ordinary_user = {'username': 'test-user'}
        moderator = {'username': 'test-admin'}
        # set up attachment
        f = os.path.join(os.path.dirname(__file__), '..', 'data', 'user.png')
        with open(f) as f:
            pic = f.read()
        self.app.post(
            self.post_link + 'attach',
            upload_files=[('file_info', 'user.png', pic)])
        # ... make sure ordinary user can see it
        r = self.app.get(self.thread_link, extra_environ=ordinary_user)
        assert '<div class="attachment_thumb">' in r
        alink = self.attach_link()
        thumblink = alink + '/thumb'
        # ... and access it
        self.app.get(alink, status=200, extra_environ=ordinary_user)
        self.app.get(thumblink, status=200, extra_environ=ordinary_user)

        # make post unmoderated
        _, slug = self.post_link.rstrip('/').rsplit('/', 1)
        post = M.Post.query.get(slug=slug)
        assert post, 'Could not find post for {} {}'.format(slug, self.post_link)
        post.status = 'pending'
        session(post).flush(post)
        # ... make sure attachment is not visible to ordinary user
        r = self.app.get(self.thread_link, extra_environ=ordinary_user)
        assert '<div class="attachment_thumb">' not in r, 'Attachment is visible on unmoderated post'
        # ... but visible to moderator
        r = self.app.get(self.thread_link, extra_environ=moderator)
        assert '<div class="attachment_thumb">' in r
        # ... and ordinary user can't access it
        self.app.get(alink, status=403, extra_environ=ordinary_user)
        self.app.get(thumblink, status=403, extra_environ=ordinary_user)
        # ... but moderator can
        self.app.get(alink, status=200, extra_environ=moderator)
        self.app.get(thumblink, status=200, extra_environ=moderator)
