# coding=utf-8
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
import datetime

from nose.tools import assert_in, assert_not_in
from ming.orm.ormsession import ThreadLocalORMSession
from tg import tmpl_context as c

from alluratest.controller import TestController
from allura import model as M
from allura.lib import helpers as h
from forgeblog import model as BM


class TestFeeds(TestController):

    def _post(self, slug='', **kw):
        d = {
            'title': 'My Pôst'.encode('utf-8'),
            'text': 'Nothing to see here',
            'labels': '',
            'state': 'published'}
        d.update(kw)
        r = self.app.post('/blog%s/save' % slug, params=d)
        return r

    def _update(self, url='', delete=False, **kw):
        if delete:
            d = {
                'delete': 'Delete'
            }
        else:
            d = {
                'title': 'My Post',
                'text': 'Nothing to see here',
                'labels': '',
                'state': 'published'}
            d.update(kw)
        r = self.app.post('/blog/' + str(self._blog_date()) + "/" + url + "/save", params=d)
        return r

    def _blog_date(self):
        return datetime.datetime.utcnow().strftime('%Y/%m')

    def test_feeds(self):
        self._post()
        r = self.app.get('/blog/feed.rss')
        r.mustcontain('/my-p%C3%B4st/</link>')
        r = self.app.get('/blog/feed.atom')
        r.mustcontain('/my-p%C3%B4st/"')

    def test_rss_feed_contains_self_link(self):
        r = self.app.get('/blog/feed.rss')
        # atom namespace included
        assert_in('<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">', r)
        # ...and atom:link points to feed url
        assert_in('<atom:link href="http://localhost/blog/feed.rss" '
                  'rel="self" type="application/rss+xml"></atom:link>', r)

    def test_post_feeds(self):
        self._post()
        d = self._blog_date()
        response = self.app.get(h.urlquote('/blog/%s/my-pôst/feed.rss' % d))
        assert 'Nothing to see' in response
        response = self.app.get(h.urlquote('/blog/%s/my-pôst/feed.atom' % d))
        assert 'Nothing to see' in response
        self._post(title='test', text='*sometext*')
        response = self.app.get('/blog/feed')
        assert_in('&lt;div class="markdown_content"&gt;&lt;p&gt;&lt;em&gt;sometext&lt;/em&gt;&lt;/p&gt;&lt;/div&gt;',
                  response)

    def test_related_artifacts(self):
        self._post(title='one')
        M.MonQTask.run_ready()
        d = self._blog_date()
        self._post(title='two', text='[blog:%s/one]' % d)
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/blog/%s/one/' % d)
        assert 'Related' in r
        assert 'Blog: %s/two' % d in r

    def test_feed_update(self):
        # Post a feed.
        d = self._blog_date()
        self._post(title="Hello World")
        response = self.app.get('/blog/%s/hello-world/feed.rss' % d)
        assert "Nothing to see here" in response
        # Update it with different data.
        r = self._update(url='hello-world', text="Everything is here")
        # Check if the feed changed.
        response = self.app.get('/blog/%s/hello-world/feed.rss' % d)
        assert "Everything is here" in response
        assert "Nothing to see here" not in response
        # Change the status to draft.
        response = self.app.get('/blog/')
        assert "Everything is here" in response
        self._update(url='hello-world', status="draft")
        response = self.app.get('/blog/')
        assert "Everything is here" not in response

    def test_post_delete_feed_delete(self):
        # Post a blogpost.
        self._post(title="Deletion Post")
        d = self._blog_date()
        url = '/blog/' + self._blog_date() + "/deletion-post/"
        # Check that post exists.
        response = self.app.get("/blog/")
        assert '/blog/%s/deletion-post/edit' % d in response
        response = self.app.get("/blog/feed.rss")
        assert url in response
        # Delete the post.
        self._update(url="deletion-post", delete=True)
        # Check feed is deleted.
        response = self.app.get("/blog/")
        assert '/blog/%s/deletion-post/edit' % d not in response
        response = self.app.get("/blog/feed.rss")
        assert url not in response

    def test_comments_only_in_per_post_feed(self):
        self._post()
        blog_post = BM.BlogPost.query.get()
        with h.push_config(c, user=M.User.query.get(username='test-admin')), \
             h.push_context(blog_post.project._id, app_config_id=blog_post.app_config_id):
            blog_post.discussion_thread.add_post(text='You are a good blogger, I am a boring commentor.')
        ThreadLocalORMSession.flush_all()

        resp = self.app.get(h.urlquote("/blog/" + self._blog_date() + "/my-pôst/feed.rss"))
        assert_in('boring comment', resp)

        resp = self.app.get("/blog/feed.rss")
        assert_not_in('boring comment', resp)