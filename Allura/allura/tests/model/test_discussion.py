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

"""
Model tests for artifact
"""
from io import BytesIO
import time
from datetime import datetime, timedelta
from cgi import FieldStorage

from tg import tmpl_context as c
import mock
from mock import patch

from ming.orm import session, ThreadLocalORMSession
from webob import exc

from allura import model as M
from allura.lib import helpers as h
from allura.tests import TestController
from alluratest.controller import setup_global_objects


class TestDiscussion:

    def setup_method(self):
        controller = TestController()
        controller.setup_method(None)
        controller.app.get('/wiki/Home/')
        setup_global_objects()
        ThreadLocalORMSession.close_all()
        h.set_context('test', 'wiki', neighborhood='Projects')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    @classmethod
    def teardown_class(cls):
        ThreadLocalORMSession.close_all()

    def test_discussion_methods(self):
        d = M.Discussion(shortname='test', name='test')
        assert d.thread_class() == M.Thread
        assert d.post_class() == M.Post
        assert d.attachment_class() == M.DiscussionAttachment
        ThreadLocalORMSession.flush_all()
        d.update_stats()
        ThreadLocalORMSession.flush_all()
        assert d.last_post is None
        assert d.url().endswith('wiki/_discuss/')
        assert d.index()['name_s'] == 'test'
        assert d.find_posts().count() == 0
        jsn = d.__json__()
        assert jsn['name'] == d.name
        d.delete()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_thread_methods(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
        assert t.discussion_class() == M.Discussion
        assert t.post_class() == M.Post
        assert t.attachment_class() == M.DiscussionAttachment
        p0 = t.post('This is a post')
        p1 = t.post('This is another post')
        time.sleep(0.25)
        t.post('This is a reply', parent_id=p0._id)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        d = M.Discussion.query.get(shortname='test')
        t = d.threads[0]
        assert d.last_post is not None
        assert t.last_post is not None
        t.create_post_threads(t.posts)
        posts0 = t.find_posts(page=0, limit=10, style='threaded')
        posts1 = t.find_posts(page=0, limit=10, style='timestamp')
        assert posts0 != posts1
        ts = p0.timestamp.replace(
            microsecond=int(p0.timestamp.microsecond // 1000) * 1000)
        posts2 = t.find_posts(page=0, limit=10, style='threaded', timestamp=ts)
        assert len(posts2) > 0

        assert 'wiki/_discuss/' in t.url()
        assert t.index()['views_i'] == 0
        assert t.post_count == 3
        jsn = t.__json__()
        assert '_id' in jsn
        assert len(jsn['posts']) == 3
        (p.approve() for p in (p0, p1))
        ThreadLocalORMSession.flush_all()
        assert t.num_replies == 3
        t.spam()
        assert t.num_replies == 0
        ThreadLocalORMSession.flush_all()
        assert len(t.find_posts()) == 0
        t.delete()

    def test_thread_new(self):
        with mock.patch('allura.model.discuss.h.nonce') as nonce:
            nonce.side_effect = ['deadbeef', 'deadbeef', 'beefdead']
            d = M.Discussion(shortname='test', name='test')
            t1 = M.Thread.new(discussion_id=d._id, subject='Test Thread One')
            t2 = M.Thread.new(discussion_id=d._id, subject='Test Thread Two')
            ThreadLocalORMSession.flush_all()
            session(t1).expunge(t1)
            session(t2).expunge(t2)
            t1_2 = M.Thread.query.get(_id=t1._id)
            t2_2 = M.Thread.query.get(_id=t2._id)
            assert t1._id == 'deadbeef'
            assert t2._id == 'beefdead'
            assert t1_2.subject == 'Test Thread One'
            assert t2_2.subject == 'Test Thread Two'

    def test_post_methods(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
        p = t.post('This is a post')
        p2 = t.post('This is another post')
        assert p.discussion_class() == M.Discussion
        assert p.thread_class() == M.Thread
        assert p.attachment_class() == M.DiscussionAttachment
        p.commit()
        assert p.parent is None
        assert p.subject == 'Test Thread'
        assert p.attachments == []
        assert 'wiki/_discuss' in p.url()
        assert p.reply_subject() == 'Re: Test Thread'
        assert p.link_text() == p.subject

        ss = p.history().first()
        assert 'version' in h.get_first(ss.index(), 'title')
        assert '#' in ss.shorthand_id()

        jsn = p.__json__()
        assert jsn["thread_id"] == t._id

        (p.approve() for p in (p, p2))
        ThreadLocalORMSession.flush_all()
        assert t.num_replies == 2
        p.spam()
        assert t.num_replies == 1
        p.undo('ok')
        assert t.num_replies == 2
        p.delete()
        assert t.num_replies == 1

    def test_attachment_methods(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
        p = t.post('This is a post')
        p_att = p.attach('foo.text', BytesIO(b'Hello, world!'),
                         discussion_id=d._id,
                         thread_id=t._id,
                         post_id=p._id)
        t_att = p.attach('foo2.text', BytesIO(b'Hello, thread!'),
                         discussion_id=d._id,
                         thread_id=t._id)
        d_att = p.attach('foo3.text', BytesIO(b'Hello, discussion!'),
                         discussion_id=d._id)

        ThreadLocalORMSession.flush_all()
        assert p_att.post == p
        assert p_att.thread == t
        assert p_att.discussion == d
        for att in (p_att, t_att, d_att):
            assert 'wiki/_discuss' in att.url()
            assert 'attachment/' in att.url()

        # Test notification in mail
        t = M.Thread.new(discussion_id=d._id, subject='Test comment notification')
        fs = FieldStorage()
        fs.name = 'file_info'
        fs.filename = 'fake.txt'
        fs.type = 'text/plain'
        fs.file = BytesIO(b'this is the content of the fake file\n')
        p = t.post(text='test message', forum=None, subject='', file_info=fs)
        ThreadLocalORMSession.flush_all()
        n = M.Notification.query.get(
            subject='[test:wiki] Test comment notification')
        url = h.absurl(f'{p.url()}attachment/{fs.filename}')
        assert (
            '\nAttachments:\n\n'
            '- [fake.txt]({}) (37 Bytes; text/plain)'.format(url) in
            n.text)

    def test_multiple_attachments(self):
        test_file1 = FieldStorage()
        test_file1.name = 'file_info'
        test_file1.filename = 'test1.txt'
        test_file1.type = 'text/plain'
        test_file1.file = BytesIO(b'test file1\n')
        test_file2 = FieldStorage()
        test_file2.name = 'file_info'
        test_file2.filename = 'test2.txt'
        test_file2.type = 'text/plain'
        test_file2.file = BytesIO(b'test file2\n')
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
        test_post = t.post('test post')
        test_post.add_multiple_attachments([test_file1, test_file2])
        ThreadLocalORMSession.flush_all()
        assert len(test_post.attachments) == 2
        attaches = test_post.attachments
        assert 'test1.txt' in [attaches[0].filename, attaches[1].filename]
        assert 'test2.txt' in [attaches[0].filename, attaches[1].filename]

    def test_add_attachment(self):
        test_file = FieldStorage()
        test_file.name = 'file_info'
        test_file.filename = 'test.txt'
        test_file.type = 'text/plain'
        test_file.file = BytesIO(b'test file\n')
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
        test_post = t.post('test post')
        test_post.add_attachment(test_file)
        ThreadLocalORMSession.flush_all()
        assert len(test_post.attachments) == 1
        attach = test_post.attachments[0]
        assert attach.filename == 'test.txt', attach.filename
        assert attach.content_type == 'text/plain', attach.content_type

    def test_notification_two_attaches(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread.new(discussion_id=d._id, subject='Test comment notification')
        fs1 = FieldStorage()
        fs1.name = 'file_info'
        fs1.filename = 'fake.txt'
        fs1.type = 'text/plain'
        fs1.file = BytesIO(b'this is the content of the fake file\n')
        fs2 = FieldStorage()
        fs2.name = 'file_info'
        fs2.filename = 'fake2.txt'
        fs2.type = 'text/plain'
        fs2.file = BytesIO(b'this is the content of the fake file\n')
        p = t.post(text='test message', forum=None, subject='', file_info=[fs1, fs2])
        ThreadLocalORMSession.flush_all()
        n = M.Notification.query.get(
            subject='[test:wiki] Test comment notification')
        base_url = h.absurl(f'{p.url()}attachment/')
        assert (
            '\nAttachments:\n\n'
            '- [fake.txt]({0}fake.txt) (37 Bytes; text/plain)\n'
            '- [fake2.txt]({0}fake2.txt) (37 Bytes; text/plain)'.format(base_url) in
            n.text)

    def test_discussion_delete(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
        p = t.post('This is a post')
        p.attach('foo.text', BytesIO(b''),
                 discussion_id=d._id,
                 thread_id=t._id,
                 post_id=p._id)
        M.ArtifactReference.from_artifact(d)
        rid = d.index_id()
        ThreadLocalORMSession.flush_all()
        d.delete()
        ThreadLocalORMSession.flush_all()
        assert M.ArtifactReference.query.find(dict(_id=rid)).count() == 0

    def test_thread_delete(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
        p = t.post('This is a post')
        p.attach('foo.text', BytesIO(b''),
                 discussion_id=d._id,
                 thread_id=t._id,
                 post_id=p._id)
        ThreadLocalORMSession.flush_all()
        t.delete()

    def test_post_delete(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
        p = t.post('This is a post')
        p.attach('foo.text', BytesIO(b''),
                 discussion_id=d._id,
                 thread_id=t._id,
                 post_id=p._id)
        ThreadLocalORMSession.flush_all()
        p.delete()

    def test_post_undo(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
        p = t.post('This is a post')
        t.post('This is a post2')
        t.post('This is a post3')
        ThreadLocalORMSession.flush_all()
        assert t.num_replies == 3
        p.spam()
        assert t.num_replies == 2
        p.undo('ok')
        assert t.num_replies == 3

    def test_post_permission_check(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
        c.user = M.User.anonymous()
        try:
            t.post('This post will fail the check.')
            assert False, "Expected an anonymous post to fail."
        except exc.HTTPUnauthorized:
            pass
        t.post('This post will pass the check.', ignore_security=True)

    def test_post_url_paginated(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread(discussion_id=d._id, subject='Test Thread')
        p = []  # posts in display order
        ts = datetime.utcnow() - timedelta(days=1)
        for i in range(5):
            ts += timedelta(minutes=1)
            p.append(t.post('This is a post #%s' % i, timestamp=ts))

        ts += timedelta(minutes=1)
        p.insert(1, t.post(
            'This is reply #0 to post #0', parent_id=p[0]._id, timestamp=ts))

        ts += timedelta(minutes=1)
        p.insert(2, t.post(
            'This is reply #1 to post #0', parent_id=p[0]._id, timestamp=ts))

        ts += timedelta(minutes=1)
        p.insert(4, t.post(
            'This is reply #0 to post #1', parent_id=p[3]._id, timestamp=ts))

        ts += timedelta(minutes=1)
        p.insert(6, t.post(
            'This is reply #0 to post #2', parent_id=p[5]._id, timestamp=ts))

        ts += timedelta(minutes=1)
        p.insert(7, t.post(
            'This is reply #1 to post #2', parent_id=p[5]._id, timestamp=ts))

        ts += timedelta(minutes=1)
        p.insert(8, t.post(
            'This is reply #0 to reply #1 to post #2',
            parent_id=p[7]._id, timestamp=ts))

        # with default paging limit
        for _p in p:
            url = t.url() + '?limit=25#' + _p.slug
            assert _p.url_paginated() == url, _p.url_paginated()

        # with user paging limit
        limit = 3
        c.user.set_pref('results_per_page', limit)
        for i, _p in enumerate(p):
            page = i // limit
            url = t.url() + '?limit=%s' % limit
            if page > 0:
                url += '&page=%s' % page
            url += '#' + _p.slug
            assert _p.url_paginated() == url

    def test_post_url_paginated_with_artifact(self):
        """Post.url_paginated should return link to attached artifact, if any"""
        from forgewiki.model import Page
        page = Page.upsert(title='Test Page')
        thread = page.discussion_thread
        comment = thread.post('Comment')
        url = page.url() + '?limit=25#' + comment.slug
        assert comment.url_paginated() == url

    def test_post_notify(self):
        d = M.Discussion(shortname='test', name='test')
        d.monitoring_email = 'darthvader@deathstar.org'
        t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
        with patch('allura.model.notification.Notification.send_simple') as send:
            t.post('This is a post')
            send.assert_called_with(d.monitoring_email)

        c.app.config.project.notifications_disabled = True
        with patch('allura.model.notification.Notification.send_simple') as send:
            t.post('Another post')
            try:
                send.assert_called_with(d.monitoring_email)
            except AssertionError:
                pass  # method not called as expected
            else:
                assert False, 'send_simple must not be called'

    @patch('allura.model.discuss.c.project.users_with_role')
    def test_is_spam_for_admin(self, users):
        users.return_value = [c.user, ]
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread(discussion_id=d._id, subject='Test Thread')
        t.post('This is a post')
        post = M.Post.query.get(text='This is a post')
        assert not t.is_spam(post), t.is_spam(post)

    @patch('allura.model.discuss.c.project.users_with_role')
    def test_is_spam(self, role):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread(discussion_id=d._id, subject='Test Thread')
        role.return_value = []
        with mock.patch('allura.controllers.discuss.g.spam_checker') as spam_checker:
            spam_checker.check.return_value = True
            post = mock.Mock()
            assert t.is_spam(post), t.is_spam(post)
            assert spam_checker.check.call_count == 1, spam_checker.call_count

    @mock.patch('allura.controllers.discuss.g.spam_checker')
    def test_not_spam_and_has_unmoderated_post_permission(self, spam_checker):
        spam_checker.check.return_value = False
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread(discussion_id=d._id, subject='Test Thread')
        role = M.ProjectRole.by_name('*anonymous')._id
        post_permission = M.ACE.allow(role, 'post')
        unmoderated_post_permission = M.ACE.allow(role, 'unmoderated_post')
        t.acl.append(post_permission)
        t.acl.append(unmoderated_post_permission)
        with h.push_config(c, user=M.User.anonymous()):
            post = t.post('Hey')
        assert post.status == 'ok'

    @mock.patch('allura.controllers.discuss.g.spam_checker')
    @mock.patch.object(M.Thread, 'notify_moderators')
    def test_not_spam_but_has_no_unmoderated_post_permission(self, notify_moderators, spam_checker):
        spam_checker.check.return_value = False
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread(discussion_id=d._id, subject='Test Thread')
        role = M.ProjectRole.by_name('*anonymous')._id
        post_permission = M.ACE.allow(role, 'post')
        t.acl.append(post_permission)
        with h.push_config(c, user=M.User.anonymous()):
            post = t.post('Hey')
        assert post.status == 'pending'
        assert notify_moderators.call_count == 1

    @mock.patch('allura.controllers.discuss.g.spam_checker')
    @mock.patch.object(M.Thread, 'notify_moderators')
    def test_spam_and_has_unmoderated_post_permission(self, notify_moderators, spam_checker):
        spam_checker.check.return_value = True
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread(discussion_id=d._id, subject='Test Thread')
        role = M.ProjectRole.by_name('*anonymous')._id
        post_permission = M.ACE.allow(role, 'post')
        unmoderated_post_permission = M.ACE.allow(role, 'unmoderated_post')
        t.acl.append(post_permission)
        t.acl.append(unmoderated_post_permission)
        with h.push_config(c, user=M.User.anonymous()):
            post = t.post('Hey')
        assert post.status == 'pending'
        assert notify_moderators.call_count == 1

    @mock.patch('allura.controllers.discuss.g.spam_checker')
    def test_thread_subject_not_included_in_text_checked(self, spam_checker):
        spam_checker.check.return_value = False
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread(discussion_id=d._id, subject='Test Thread')
        t.post('Hello')
        assert spam_checker.check.call_count == 1
        assert spam_checker.check.call_args[0][0] == 'Hello'

    def test_post_count(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread(discussion_id=d._id, subject='Test Thread')
        M.Post(discussion_id=d._id, thread_id=t._id, status='spam')
        M.Post(discussion_id=d._id, thread_id=t._id, status='ok')
        M.Post(discussion_id=d._id, thread_id=t._id, status='pending')
        ThreadLocalORMSession.flush_all()
        assert t.post_count == 2

    @mock.patch('allura.controllers.discuss.g.spam_checker')
    def test_spam_num_replies(self, spam_checker):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread(discussion_id=d._id, subject='Test Thread', num_replies=2)
        M.Post(discussion_id=d._id, thread_id=t._id, status='ok')
        ThreadLocalORMSession.flush_all()
        p1 = M.Post(discussion_id=d._id, thread_id=t._id, status='spam')
        p1.spam()
        assert t.num_replies == 1

    def test_deleted_thread_index(self):
        d = M.Discussion(shortname='test', name='test')
        t = M.Thread(discussion_id=d._id, subject='Test Thread')
        p = M.Post(discussion_id=d._id, thread_id=t._id, status='ok')
        t.delete()
        ThreadLocalORMSession.flush_all()

        # re-query, so relationships get reloaded
        ThreadLocalORMSession.close_all()
        p = M.Post.query.get(_id=p._id)

        # just make sure this doesn't fail
        p.index()
