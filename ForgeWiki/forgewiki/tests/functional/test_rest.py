import json

from nose.tools import assert_equal

from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase


class TestWikiApi(TestRestApiBase):

    def setUp(self):
        super(TestWikiApi, self).setUp()
        self.setup_with_tools()

    @td.with_wiki
    def setup_with_tools(self):
        h.set_context('test', 'wiki', neighborhood='Projects')

    def test_get_page(self):
        r = self.app.get('/p/test/wiki/Home/')
        discussion_url = r.html.findAll('form')[2]['action'][:-4]
        content = file(__file__).read()
        self.app.post('/wiki/Home/attach', upload_files=[('file_info', 'test_root.py', content)])
        r = self.app.get('/rest/p/test/wiki/Home/')
        r = json.loads(r.body)
        assert_equal(r['attachments'][0]['url'], 'http://localhost:80/p/test/wiki/Home/attachment/test_root.py')
        assert_equal(r['discussion_thread_url'], 'http://localhost:80/rest%s' % discussion_url)
        assert_equal(r['discussion_thread']['_id'], discussion_url.split('/')[-2])
        self.app.post('/wiki/Home/attach', upload_files=[('file_info', '__init__.py', content),])
        r = self.app.get('/rest/p/test/wiki/Home/')
        r = json.loads(r.body)
        assert_equal(len(r['attachments']), 2)

    def test_post_page(self):
        data = {
            'text': 'Embrace the Dark Side',
            'labels': 'head hunting,dark side'
        }
        r = self.api_post('/rest/p/test/wiki/Home/', **data)
        assert_equal(r.status_int, 200)
        r = self.api_get('/rest/p/test/wiki/Home/')
        assert_equal(r.json['text'], data['text'])
        assert_equal(r.json['labels'], data['labels'].split(','))
