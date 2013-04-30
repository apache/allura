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

"""
Model tests for artifact
"""
from cStringIO import StringIO
import time
from datetime import datetime, timedelta
from cgi import FieldStorage

from pylons import tmpl_context as c, app_globals as g
from pylons import request, response
from nose.tools import assert_raises, assert_equals, with_setup
import mock
from mock import patch

from ming.orm import session, ThreadLocalORMSession
from webob import Request, Response, exc

from allura import model as M
from allura.lib.app_globals import Globals
from allura.lib import helpers as h
from allura.tests import TestController
from alluratest.controller import setup_global_objects

def setUp():
    controller = TestController()
    controller.setUp()
    controller.app.get('/wiki/Home/')
    setup_global_objects()
    ThreadLocalORMSession.close_all()
    h.set_context('test', 'wiki', neighborhood='Projects')
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()


def tearDown():
    ThreadLocalORMSession.close_all()

@with_setup(setUp, tearDown)
def test_discussion_methods():
    d = M.Discussion(shortname='test', name='test')
    assert d.thread_class() == M.Thread
    assert d.post_class() == M.Post
    assert d.attachment_class() == M.DiscussionAttachment
    ThreadLocalORMSession.flush_all()
    d.update_stats()
    ThreadLocalORMSession.flush_all()
    assert d.last_post == None
    assert d.url().endswith('wiki/_discuss/')
    assert d.index()['name_s'] == 'test'
    assert d.subscription() == None
    assert d.find_posts().count() == 0
    jsn = d.__json__()
    assert jsn['name'] == d.name
    d.delete()
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()

@with_setup(setUp, tearDown)
def test_thread_methods():
    d = M.Discussion(shortname='test', name='test')
    t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
    assert t.discussion_class() == M.Discussion
    assert t.post_class() == M.Post
    assert t.attachment_class() == M.DiscussionAttachment
    p0 = t.post('This is a post')
    p1 = t.post('This is another post')
    time.sleep(0.25)
    p2 = t.post('This is a reply', parent_id=p0._id)
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
    assert not t.subscription
    t.subscription = True
    assert t.subscription
    t.subscription = False
    assert not t.subscription
    assert t.top_level_posts().count() == 2
    assert t.post_count == 3
    jsn = t.__json__()
    assert '_id' in jsn
    assert_equals(len(jsn['posts']), 3)
    (p.approve() for p in (p0, p1))
    assert t.num_replies == 2
    t.spam()
    assert t.num_replies == 0
    ThreadLocalORMSession.flush_all()
    assert len(t.find_posts()) == 0
    t.delete()

@with_setup(setUp, tearDown)
def test_thread_new():
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
        assert_equals(t1._id, 'deadbeef')
        assert_equals(t2._id, 'beefdead')
        assert_equals(t1_2.subject, 'Test Thread One')
        assert_equals(t2_2.subject, 'Test Thread Two')

@with_setup(setUp, tearDown)
def test_post_methods():
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
    assert p.attachments.count() == 0
    assert 'wiki/_discuss' in p.url()
    assert p.reply_subject() == 'Re: Test Thread'
    assert p.link_text() == p.subject

    ss = p.history().first()
    assert 'version' in h.get_first(ss.index(), 'title')
    assert '#' in ss.shorthand_id()

    jsn = p.__json__()
    assert jsn["thread_id"] == t._id

    (p.approve() for p in (p, p2))
    assert t.num_replies == 1
    p2.spam()
    assert t.num_replies == 0
    p.spam()
    assert t.num_replies == 0
    p.delete()
    assert t.num_replies == 0

@with_setup(setUp, tearDown)
def test_attachment_methods():
    d = M.Discussion(shortname='test', name='test')
    t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
    p = t.post('This is a post')
    p_att = p.attach('foo.text', StringIO('Hello, world!'),
                discussion_id=d._id,
                thread_id=t._id,
                post_id=p._id)
    t_att = p.attach('foo2.text', StringIO('Hello, thread!'),
                discussion_id=d._id,
                thread_id=t._id)
    d_att = p.attach('foo3.text', StringIO('Hello, discussion!'),
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
    fs.name='file_info'
    fs.filename='fake.txt'
    fs.type = 'text/plain'
    fs.file=StringIO('this is the content of the fake file\n')
    p = t.post(text=u'test message', forum= None, subject= '', file_info=fs)
    ThreadLocalORMSession.flush_all()
    n = M.Notification.query.get(subject=u'[test:wiki] Test comment notification')
    assert '\nAttachment: fake.txt (37 Bytes; text/plain)' in n.text

@with_setup(setUp, tearDown)
def test_add_attachment():
    test_file = FieldStorage()
    test_file.name = 'file_info'
    test_file.filename = 'test.txt'
    test_file.type = 'text/plain'
    test_file.file=StringIO('test file\n')
    d = M.Discussion(shortname='test', name='test')
    t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
    test_post = t.post('test post')
    test_post.add_attachment(test_file)
    ThreadLocalORMSession.flush_all()
    assert test_post.attachments.count() == 1, test_post.attachments.count()
    attach = test_post.attachments.first()
    assert attach.filename == 'test.txt', attach.filename
    assert attach.content_type == 'text/plain', attach.content_type

@with_setup(setUp, tearDown)
def test_discussion_delete():
    d = M.Discussion(shortname='test', name='test')
    t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
    p = t.post('This is a post')
    p.attach('foo.text', StringIO(''),
                discussion_id=d._id,
                thread_id=t._id,
                post_id=p._id)
    r = M.ArtifactReference.from_artifact(d)
    rid = d.index_id()
    ThreadLocalORMSession.flush_all()
    d.delete()
    ThreadLocalORMSession.flush_all()
    assert_equals(M.ArtifactReference.query.find(dict(_id=rid)).count(), 0)

@with_setup(setUp, tearDown)
def test_thread_delete():
    d = M.Discussion(shortname='test', name='test')
    t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
    p = t.post('This is a post')
    p.attach('foo.text', StringIO(''),
                discussion_id=d._id,
                thread_id=t._id,
                post_id=p._id)
    ThreadLocalORMSession.flush_all()
    t.delete()

@with_setup(setUp, tearDown)
def test_post_delete():
    d = M.Discussion(shortname='test', name='test')
    t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
    p = t.post('This is a post')
    p.attach('foo.text', StringIO(''),
                discussion_id=d._id,
                thread_id=t._id,
                post_id=p._id)
    ThreadLocalORMSession.flush_all()
    p.delete()

@with_setup(setUp, tearDown)
def test_post_permission_check():
    d = M.Discussion(shortname='test', name='test')
    t = M.Thread.new(discussion_id=d._id, subject='Test Thread')
    c.user = M.User.anonymous()
    try:
        p1 = t.post('This post will fail the check.')
        assert False, "Expected an anonymous post to fail."
    except exc.HTTPUnauthorized:
        pass
    p2 = t.post('This post will pass the check.', ignore_security=True)


@with_setup(setUp, tearDown)
def test_post_url_paginated():
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
        url = t.url() + '?limit=50#' + _p.slug
        assert _p.url_paginated() == url, _p.url_paginated()

    # with user paging limit
    limit = 3
    c.user.set_pref('results_per_page', limit)
    for i, _p in enumerate(p):
        page = i / limit
        url = t.url() + '?limit=%s' % limit
        if page > 0:
            url += '&page=%s' % page
        url += '#' + _p.slug
        assert _p.url_paginated() == url, _p.url_paginated()


@with_setup(setUp, tearDown)
def test_post_url_paginated_with_artifact():
    """Post.url_paginated should return link to attached artifact, if any"""
    from forgewiki.model import Page
    page = Page.upsert(title='Test Page')
    thread = page.discussion_thread
    comment = thread.post('Comment')
    url = page.url() + '?limit=50#' + comment.slug
    assert_equals(comment.url_paginated(), url)


@with_setup(setUp, tearDown)
def test_post_notify():
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
