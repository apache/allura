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

import datetime
import json

import tg
from mock import patch

from allura.lib import helpers as h
from alluratest.controller import TestController


class Test(TestController):

    def _post(self, slug='', extra_app_post_params={}, **kw):
        d = {
            'title': 'My Post',
            'text': 'Nothing to see here',
            'labels': '',
            'state': 'published'}
        d.update(kw)
        r = self.app.post('/blog%s/save' % slug, params=d, **extra_app_post_params)
        return r

    def _blog_date(self):
        return datetime.datetime.utcnow().strftime('%Y/%m')

    @patch('forgeblog.model.blog.g.director.create_activity')
    def test_activity(self, create_activity):
        self._post(state='draft')
        assert create_activity.call_count == 0
        slug = '/%s/my-post' % self._blog_date()
        self._post(slug)
        assert create_activity.call_count == 1, create_activity.call_count
        assert create_activity.call_args[0][1] == 'created'
        create_activity.reset_mock()
        self._post(slug, text='new text')
        assert create_activity.call_count == 1
        assert create_activity.call_args[0][1] == 'modified'
        create_activity.reset_mock()
        self._post(slug, title='new title')
        assert create_activity.call_count == 1
        assert create_activity.call_args[0][1] == 'renamed'

    def test_root_index(self):
        self._post()
        d = self._blog_date()
        response = self.app.get('/blog/')
        assert 'Recent posts' in response
        assert 'Nothing to see here' in response
        assert '/blog/%s/my-post/edit' % d in response
        anon_r = self.app.get('/blog/',
                              extra_environ=dict(username='*anonymous'))
        # anonymous user can't see Edit links
        assert 'Nothing to see here' in anon_r
        assert '/blog/%s/my-post/edit' % d not in anon_r

    def test_root_index_draft(self):
        self._post(state='draft')
        d = self._blog_date()
        response = self.app.get('/blog/')
        assert 'Recent posts' in response
        assert 'Nothing to see here' in response
        assert 'Draft' in response
        assert '/blog/%s/my-post/edit' % d in response
        anon_r = self.app.get('/blog/',
                              extra_environ=dict(username='*anonymous'))
        # anonymous user can't see draft posts
        assert 'Nothing to see here' not in anon_r

    def test_root_new_post(self):
        response = self.app.get('/blog/new')
        assert '<option selected value="published">Published</option>' in response
        assert 'Enter your title here' in response

    def test_validation(self):
        r = self._post(title='')
        assert 'You must provide a Title' in r

    def test_root_new_search(self):
        self._post()
        response = self.app.get('/blog/search/?q=see')
        assert 'Search' in response

    def test_paging(self):
        [self._post() for i in range(3)]
        r = self.app.get('/blog/?limit=1&page=0')
        assert 'Newer Entries' not in r
        assert 'Older Entries' in r
        r = self.app.get('/blog/?limit=1&page=1')
        assert 'Newer Entries' in r
        assert 'Older Entries' in r
        r = self.app.get('/blog/?limit=1&page=2')
        assert 'Newer Entries' in r
        assert 'Older Entries' not in r

    def test_discussion_admin(self):
        r = self.app.get('/blog/')
        r = self.app.get('/admin/blog/options', validate_chunk=True)
        assert 'Allow discussion/commenting on posts' in r
        # Turn discussion on
        r = self.app.post('/admin/blog/set_options',
                          params=dict(show_discussion='1'))
        self._post()
        d = self._blog_date()
        r = self.app.get('/blog/%s/my-post/' % d)
        assert '<div class="markdown_edit">' in r
        # Turn discussion off
        r = self.app.post('/admin/blog/set_options')
        r = self.app.get('/blog/%s/my-post/' % d)
        assert '<div class="markdown_edit">' not in r

    def test_post_index(self):
        self._post()
        d = self._blog_date()
        response = self.app.get('/blog/%s/my-post/' % d)
        assert 'Nothing to see here' in response
        assert '/blog/%s/my-post/edit' % d in response
        anon_r = self.app.get('/blog/%s/my-post/' % d,
                              extra_environ=dict(username='*anonymous'))
        # anonymous user can't see Edit links
        assert 'Nothing to see here' in anon_r
        assert '/blog/%s/my-post/edit' % d not in anon_r
        self.app.get('/blog/%s/no-my-post' % d, status=404)

    def test_post_index_draft(self):
        self._post(state='draft')
        d = self._blog_date()
        response = self.app.get('/blog/%s/my-post/' % d)
        assert 'Nothing to see here' in response
        assert 'Draft' in response
        assert '/blog/%s/my-post/edit' % d in response
        anon_r = self.app.get('/blog/%s/my-post/' % d,
                              extra_environ=dict(username='*anonymous'))
        # anonymous user can't get to draft posts
        assert 'Nothing to see here' not in anon_r

    def test_post_edit(self):
        self._post()
        d = self._blog_date()
        response = self.app.get('/blog/%s/my-post/edit' % d)
        assert 'Nothing' in response
        # anon users can't edit
        response = self.app.get('/blog/%s/my-post/edit' % d,
                                extra_environ=dict(username='*anonymous'))
        assert 'Nothing' not in response

    def test_post_get_markdown(self):
        self._post()
        d = self._blog_date()
        response = self.app.get('/blog/%s/my-post/get_markdown' % d)
        assert 'Nothing' in response

    def test_post_update_markdown(self):
        self._post()
        d = self._blog_date()
        response = self.app.post(
            '/blog/%s/my-post/update_markdown' % d,
            params={
                'text': '- [x] checkbox'})
        assert response.json['status'] == 'success'
        # anon users can't edit markdown
        response = self.app.post(
            '/blog/%s/my-post/update_markdown' % d,
            params={
                'text': '- [x] checkbox'},
            extra_environ=dict(username='*anonymous'))
        assert response.json['status'] == 'no_permission'

    def test_post_attachments(self):
        # create
        upload = ('attachment', 'nums.txt', b'123412341234')
        upload2 = ('attachment', 'more_nums.txt', b'56789')
        self._post(extra_app_post_params=dict(upload_files=[upload, upload2]))

        # check it is listed
        d = self._blog_date()
        r = self.app.get('/blog/%s/my-post/' % d)
        assert 'nums.txt' in r

        # edit
        slug = '/%s/my-post' % d
        upload = ('attachment', 'letters.txt', b'abcdefghij')
        self._post(slug=slug,
                   extra_app_post_params=dict(upload_files=[upload]))

        # check both are there
        r = self.app.get('/blog/%s/my-post/' % d)
        assert 'nums.txt' in r
        assert 'letters.txt' in r

        # check attachment is accessible
        r = self.app.get('/blog/%s/my-post/attachment/letters.txt' % d)
        assert 'abcdefghij' in r

    def test_post_history(self):
        self._post()
        d = self._blog_date()
        self._post('/%s/my-post' % d)
        self._post('/%s/my-post' % d)
        response = self.app.get('/blog/%s/my-post/history' % d)
        assert 'My Post' in response
        # two revisions are shown
        assert '2 by Test Admin' in response
        assert '1 by Test Admin' in response
        self.app.get('/blog/%s/my-post/?version=1' % d)
        self.app.get('/blog/%s/my-post/?version=foo' % d, status=404)

    def test_post_diff(self):
        self._post()
        d = self._blog_date()
        self._post('/%s/my-post' % d, text='sometext\n<script>alert(1)</script>')
        self.app.post('/blog/%s/my-post/revert' % d, params=dict(version='1'))
        response = self.app.get('/blog/%s/my-post/diff?v2=2&v1=1' % d)
        assert 'My Post' in response
        assert '<del> Nothing to see here </del> <ins> sometext </ins>' in response
        assert '<script>alert' not in response
        assert '<ins> &lt;script&gt;alert' in response

    def test_post_revert(self):
        self._post()
        d = self._blog_date()
        self._post('/%s/my-post' % d, text='sometést'.encode())
        response = self.app.post('/blog/%s/my-post/revert' % d, params=dict(version='1'))
        assert '.' in response.json['location']
        response = self.app.get('/blog/%s/my-post/' % d)
        assert 'Nothing to see here' in response

    def test_invalid_lookup(self):
        r = self.app.get('/blog/favicon.ico', status=404)

    def test_index_bad_url_params(self):
        self.app.get('/blog/?limit=blah&page=2x', status=200)

    def test_post_bad_url_params(self):
        self._post()
        d = self._blog_date()
        self.app.get('/blog/%s/my-post/?limit=blah&page=2x' % d, status=200)

    def test_rate_limit_submit(self):
        with h.push_config(tg.config, **{'forgeblog.rate_limits': '{"3600": 0}'}):
            r = self._post()
            wf = json.loads(self.webflash(r))
            assert wf['status'] == 'error'
            assert wf['message'] == 'Create/edit rate limit exceeded. Please try again later.'

    def test_rate_limit_form(self):
        with h.push_config(tg.config, **{'forgeblog.rate_limits': '{"3600": 0}'}):
            r = self.app.get('/blog/new')
            wf = json.loads(self.webflash(r))
            assert wf['status'] == 'error'
            assert wf['message'] == 'Create/edit rate limit exceeded. Please try again later.'

    def test_admin_external_feed_invalid(self):
        r = self.app.get('/blog/')
        r = self.app.get('/admin/blog/exfeed')
        form = r.forms[0]
        form['new_exfeed'].value = 'asdfasdf'
        r = form.submit()
        assert 'Invalid' in self.webflash(r)

    def test_admin_external_feed_ok(self):
        # sidebar menu doesn't expose link to this, unless "forgeblog.exfeed" config is true, but can use form anyway
        r = self.app.get('/blog/')
        r = self.app.get('/admin/blog/exfeed')
        form = r.forms[0]
        form['new_exfeed'].value = 'https://example.com/feed.rss'
        r = form.submit()
        assert 'External feeds updated' in self.webflash(r)

        r = self.app.get('/admin/blog/exfeed')
        r.mustcontain('https://example.com/feed.rss')
