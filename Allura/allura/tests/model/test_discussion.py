# -*- coding: utf-8 -*-
"""
Model tests for artifact
"""
from cStringIO import StringIO
import time
from datetime import datetime

from pylons import c, g, request, response
from nose.tools import assert_raises, assert_equals, with_setup
import mock

from ming.orm.ormsession import ThreadLocalORMSession
from webob import Request, Response

from allura import model as M
from allura.lib.app_globals import Globals
from allura.lib import helpers as h
from allura.tests import TestController

def setUp():
    controller = TestController()
    controller.setUp()
    controller.app.get('/wiki/Home/')
    g._push_object(Globals())
    c._push_object(mock.Mock())
    request._push_object(Request.blank('/'))
    ThreadLocalORMSession.close_all()
    h.set_context('test', 'wiki')
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()
    c.user = M.User.query.get(username='test-admin')


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
    t = M.Thread(discussion_id=d._id, subject='Test Thread')
    assert t.discussion_class() == M.Discussion
    assert t.post_class() == M.Post
    assert t.attachment_class() == M.DiscussionAttachment
    p0 = t.post('This is a post')
    p1 = t.post('This is another post')
    time.sleep(1)
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
    posts2 = t.find_posts(page=0, limit=10, style='threaded', timestamp=p0.timestamp)
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
    t.delete()

@with_setup(setUp, tearDown)
def test_post_methods():
    d = M.Discussion(shortname='test', name='test')
    t = M.Thread(discussion_id=d._id, subject='Test Thread')
    p = t.post('This is a post')
    assert p.discussion_class() == M.Discussion
    assert p.thread_class() == M.Thread
    assert p.attachment_class() == M.DiscussionAttachment
    p.commit()
    assert p.parent is None
    assert p.subject == 'Test Thread'
    assert p.attachments.count() == 0
    assert 'Test Admin' in p.summary()
    assert 'wiki/_discuss' in p.url()
    assert p.reply_subject() == 'Re: Test Thread'

    ss = p.history().first()
    assert 'Version' in ss.index()['title_s']
    assert '#' in ss.shorthand_id()

    jsn = p.__json__()
    assert jsn["thread_id"] == t._id

    p.spam()
    p.delete()

@with_setup(setUp, tearDown)
def test_attachment_methods():
    d = M.Discussion(shortname='test', name='test')
    t = M.Thread(discussion_id=d._id, subject='Test Thread')
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

@with_setup(setUp, tearDown)
def test_discussion_delete():
    d = M.Discussion(shortname='test', name='test')
    t = M.Thread(discussion_id=d._id, subject='Test Thread')
    p = t.post('This is a post')
    p.attach('foo.text', StringIO(''),
                discussion_id=d._id,
                thread_id=t._id,
                post_id=p._id)
    ThreadLocalORMSession.flush_all()
    d.delete()

@with_setup(setUp, tearDown)
def test_thread_delete():
    d = M.Discussion(shortname='test', name='test')
    t = M.Thread(discussion_id=d._id, subject='Test Thread')
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
    t = M.Thread(discussion_id=d._id, subject='Test Thread')
    p = t.post('This is a post')
    p.attach('foo.text', StringIO(''),
                discussion_id=d._id,
                thread_id=t._id,
                post_id=p._id)
    ThreadLocalORMSession.flush_all()
    p.delete()


