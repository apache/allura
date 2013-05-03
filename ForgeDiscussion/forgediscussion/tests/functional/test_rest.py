# coding: utf-8
from nose.tools import assert_equal

from allura.lib import helpers as h
from allura.tests import decorators as td
from allura import model as M
from alluratest.controller import TestRestApiBase
from forgediscussion.model import ForumThread


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
        r.forms[1]['add_forum.shortname'] = 'héllo'
        r.forms[1]['add_forum.name'] = 'Say Héllo'
        r.forms[1]['add_forum.description'] = 'Say héllo here'
        r.forms[1].submit()

    def create_topic(self, forum, subject, text):
        r = self.app.get('/discussion/create_topic/')
        f = r.html.find('form', {'action': '/p/test/discussion/save_new_topic'})
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_key('name'):
                params[field['name']] = field.has_key('value') and field['value'] or ''
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
        assert_equal(forums[0]['description'], 'Forum about anything you want to talk about.')
        assert_equal(forums[0]['num_topics'], 2)
        assert_equal(forums[0]['url'], 'http://localhost:80/rest/p/test/discussion/general/')
        assert_equal(forums[0]['last_post']['subject'], 'Hi guys')
        assert_equal(forums[0]['last_post']['author'], 'test-admin')
        assert_equal(forums[0]['last_post']['text'], 'Hi boys and girls')
        assert_equal(forums[1]['name'], u'Say Héllo')
        assert_equal(forums[1]['description'], u'Say héllo here')
        assert_equal(forums[1]['num_topics'], 0)
        assert_equal(forums[1]['url'], 'http://localhost:80/rest/p/test/discussion/h%C3%A9llo/')
        assert_equal(forums[1]['last_post'], None)

    def test_forum(self):
        forum = self.api_get('/rest/p/test/discussion/general/')
        forum = forum.json['forum']
        assert_equal(forum['name'], 'General Discussion')
        assert_equal(forum['description'], 'Forum about anything you want to talk about.')
        topics = forum['topics']
        assert_equal(len(topics), 2)
        assert_equal(topics[0]['subject'], 'Hi guys')
        assert_equal(topics[0]['num_views'], 0)
        assert_equal(topics[0]['num_replies'], 1)
        assert_equal(topics[0]['last_post']['author'], 'test-admin')
        assert_equal(topics[0]['last_post']['text'], 'Hi boys and girls')
        t = ForumThread.query.find({'subject': 'Hi guys'}).first()
        url = 'http://localhost:80/rest/p/test/discussion/general/thread/%s/' % t._id
        assert_equal(topics[0]['url'], url)
        assert_equal(topics[1]['subject'], 'Let\'s talk')
        assert_equal(topics[1]['num_views'], 0)
        assert_equal(topics[1]['num_replies'], 1)
        assert_equal(topics[1]['last_post']['author'], 'test-admin')
        assert_equal(topics[1]['last_post']['text'], '1st post')
        t = ForumThread.query.find({'subject': 'Let\'s talk'}).first()
        url = 'http://localhost:80/rest/p/test/discussion/general/thread/%s/' % t._id
        assert_equal(topics[1]['url'], url)

    def test_topic(self):
        forum = self.api_get('/rest/p/test/discussion/general/')
        forum = forum.json['forum']
        assert_equal(forum['name'], 'General Discussion')
        assert_equal(forum['description'], 'Forum about anything you want to talk about.')
        topics = forum['topics']
        topic = self.api_get(topics[0]['url'][len('http://localhost:80'):])
        topic = topic.json['topic']
        assert_equal(len(topic['posts']), 1)
        assert_equal(topic['subject'], 'Hi guys')
        assert_equal(topic['posts'][0]['text'], 'Hi boys and girls')
        assert_equal(topic['posts'][0]['subject'], 'Hi guys')

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
        assert_equal(forums[0]['name'], u'Say Héllo')
        assert_equal(resp.json['count'], 2)
        assert_equal(resp.json['page'], 1)
        assert_equal(resp.json['limit'], 1)

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
                     extra_environ={'username': '*anonymous'},
                     status=401)
        self.api_get('/rest/p/test/discussion/general/')
        self.app.get('/rest/p/test/discussion/general/',
                     extra_environ={'username': '*anonymous'},
                     status=401)
        t = ForumThread.query.find({'subject': 'Hi guys'}).first()
        self.api_get('/rest/p/test/discussion/general/thread/%s/' % t._id)
        self.app.get('/rest/p/test/discussion/general/thread/%s/' % t._id,
                     extra_environ={'username': '*anonymous'},
                     status=401)
