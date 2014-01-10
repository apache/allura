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

from mock import patch

from allura.tests import TestController
from allura import model as M


class TestDiscuss(TestController):

    def test_subscribe_unsubscribe(self):
        home = self.app.get('/wiki/_discuss/')
        subscribed = [i for i in home.html.findAll('input')
                      if i.get('type') == 'checkbox'][0]
        assert 'checked' not in subscribed.attrMap
        link = [a for a in home.html.findAll('a')
                if 'thread' in a['href']][0]
        params = {
            'threads-0._id': link['href'][len('/p/test/wiki/_discuss/thread/'):-1],
            'threads-0.subscription': 'on'}
        r = self.app.post('/wiki/_discuss/subscribe',
                          params=params,
                          headers={'Referer': '/wiki/_discuss/'})
        r = r.follow()
        subscribed = [i for i in r.html.findAll('input')
                      if i.get('type') == 'checkbox'][0]
        assert 'checked' in subscribed.attrMap
        params = {
            'threads-0._id': link['href'][len('/p/test/wiki/_discuss/thread/'):-1]
        }
        r = self.app.post('/wiki/_discuss/subscribe',
                          params=params,
                          headers={'Referer': '/wiki/_discuss/'})
        r = r.follow()
        subscribed = [i for i in r.html.findAll('input')
                      if i.get('type') == 'checkbox'][0]
        assert 'checked' not in subscribed.attrMap

    def _make_post(self, text):
        home = self.app.get('/wiki/_discuss/')
        thread_link = [a for a in home.html.findAll('a')
                       if 'thread' in a['href']][0]['href']
        thread = self.app.get(thread_link)
        for f in thread.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_key('name'):
                params[field['name']] = field.has_key(
                    'value') and field['value'] or ''
        params[f.find('textarea')['name']] = text
        r = self.app.post(f['action'].encode('utf-8'), params=params,
                          headers={'Referer': thread_link.encode("utf-8")},
                          extra_environ=dict(username='root'))
        r = r.follow()
        return r

    @patch('allura.controllers.discuss.g.spam_checker.submit_spam')
    def test_post(self, submit_spam):
        home = self.app.get('/wiki/_discuss/')
        thread_link = [a for a in home.html.findAll('a')
                       if 'thread' in a['href']][0]['href']
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
            if field.has_key('name'):
                params[field['name']] = field.has_key(
                    'value') and field['value'] or ''
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
            if field.has_key('name'):
                params[field['name']] = field.has_key(
                    'value') and field['value'] or ''
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
        home = self.app.get('/wiki/_discuss/')
        thread_url = [a for a in home.html.findAll('a')
                      if 'thread' in a['href']][0]['href']
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
        assert '<span>Spam</span>' in r
        r = self.app.get('/wiki/_discuss/',
                         extra_environ={'username': 'test-user-1'})
        assert '<span>Spam</span>' not in r, 'User without moderate perm must not see Spam link'

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
        assert M.Post.query.find().count() == 0

    def test_post_paging(self):
        home = self.app.get('/wiki/_discuss/')
        thread_link = [a for a in home.html.findAll('a')
                       if 'thread' in a['href']][0]['href']
        # just make sure it doesn't 500
        r = self.app.get('%s?limit=50&page=0' % thread_link)

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
            if field.has_key('name'):
                params[field['name']] = field.has_key(
                    'value') and field['value'] or ''
        params[reply_form.find('textarea')['name']] = 'zzz'
        self.app.post(post_link, params)
        assert create_activity.call_count == 1, create_activity.call_count
        assert create_activity.call_args[0][1] == 'modified'
        r = self.app.get(thread_url)
        assert 'zzz' in str(r.html.find('div', {'class': 'display_post'}))
        assert 'Last edit: Test Admin less than 1 minute ago' in str(
            r.html.find('div', {'class': 'display_post'}))


class TestAttachment(TestController):

    def setUp(self):
        super(TestAttachment, self).setUp()
        home = self.app.get('/wiki/_discuss/')
        self.thread_link = [a['href'].encode("utf-8")
                            for a in home.html.findAll('a')
                            if 'thread' in a['href']][0]
        thread = self.app.get(self.thread_link)
        for f in thread.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        self.post_form_link = f['action'].encode('utf-8')
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_key('name'):
                params[field['name']] = field.has_key(
                    'value') and field['value'] or ''
        params[f.find('textarea')['name']] = 'Test Post'
        r = self.app.post(f['action'].encode('utf-8'), params=params,
                          headers={'Referer': self.thread_link})
        r = r.follow()
        self.post_link = str(
            r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])

    def test_attach(self):
        r = self.app.post(self.post_link + 'attach',
                          upload_files=[('file_info', 'test.txt', 'HiThere!')])
        r = self.app.get(self.thread_link)
        for alink in r.html.findAll('a'):
            if 'attachment' in alink['href']:
                alink = str(alink['href'])
                break
        else:
            assert False, 'attachment link not found'
        assert '<div class="attachment_thumb">' in r
        r = self.app.get(alink)
        assert r.content_disposition == 'attachment;filename="test.txt"', 'Attachments should force download'
        r = self.app.post(self.post_link + 'attach',
                          upload_files=[('file_info', 'test.o12', 'HiThere!')])
        r = self.app.post(alink, params=dict(delete='on'))

    @patch('allura.model.discuss.Post.notify')
    def test_reply_attach(self, notify):
        notify.return_value = True
        r = self.app.get(self.thread_link)
        post_form = r.html.find('form', {'action': self.post_link + 'reply'})
        params = dict()
        inputs = post_form.findAll('input')

        for field in inputs:
            if field.has_key('name') and (field['name'] != 'file_info'):
                params[field['name']] = field.has_key(
                    'value') and field['value'] or ''
        params[post_form.find('textarea')['name']] = 'Reply'
        r = self.app.post(self.post_link + 'reply',
                          params=params,
                          upload_files=[('file_info', 'test.txt', 'HiThere!')])
        r = self.app.get(self.thread_link)
        assert "test.txt" in r
