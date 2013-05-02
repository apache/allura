# coding: utf-8
from nose.tools import assert_equal

from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase


class TestDiscussionApiBase(TestRestApiBase):

    def setUp(self):
        super(TestDiscussionApiBase, self).setUp()
        self.setup_with_tools()

    @td.with_discussion
    def setup_with_tools(self):
        h.set_context('test', 'discussion', neighborhood='Projects')
        self.create_forum('héllo', 'Say Héllo', 'Say héllo here')
        self.create_topic('general', 'Let\'s talk', '1st post')
        self.create_topic('general', 'Hi guys', 'Hi guys')

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
        assert_equal(forums[0]['last_post']['author'], 'Test Admin')
        assert_equal(forums[1]['name'], u'Say Héllo')
        assert_equal(forums[1]['description'], u'Say héllo here')
        assert_equal(forums[1]['num_topics'], 0)
        assert_equal(forums[1]['url'], 'http://localhost:80/rest/p/test/discussion/h%C3%A9llo/')

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
        assert_equal(topics[0]['last_post']['author'], 'Test Admin')
        assert_equal(topics[1]['subject'], 'Let\'s talk')
        assert_equal(topics[1]['num_views'], 0)
        assert_equal(topics[1]['num_replies'], 1)
        assert_equal(topics[1]['last_post']['author'], 'Test Admin')
