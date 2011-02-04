import os
import Image, StringIO
import allura

from nose.tools import assert_true

from alluratest.controller import TestController
from forgeblog import model

# These are needed for faking reactor actions
import mock
from allura.lib import helpers as h
from allura.command import reactor
from allura.ext.search import search_main
from ming.orm.ormsession import ThreadLocalORMSession

#---------x---------x---------x---------x---------x---------x---------x
# RootController methods exposed:
#     index, new_page, search
# PageController methods exposed:
#     index, edit, history, diff, raw, revert, update
# CommentController methods exposed:
#     reply, delete

class TestRootController(TestController):
    def test_root_index(self):
        response = self.app.get('/blog/')
        assert 'Recent posts' in response

    def test_root_new_post(self):
        response = self.app.get('/blog/new')
        assert 'Please enter a title' in response

    def _post(self, slug='', **kw):
        d = {
                'title':'My Post',
                'text':'Nothing to see here',
                'date':'2010/08/23',
                'time':'00:00',
                'labels':'',
                'state':'published'}
        d.update(kw)
        r = self.app.post('/blog%s/save' % slug, params=d)
        return r


    def test_root_new_search(self):
        self._post()
        response = self.app.get('/blog/search?q=see')
        assert 'Search' in response

    def test_post_index(self):
        self._post()
        response = self.app.get('/blog/2010/08/my-post/')
        assert 'Nothing' in response

    def test_post_edit(self):
        self._post()
        response = self.app.get('/blog/2010/08/my-post/edit')
        assert 'Nothing' in response

    def test_post_history(self):
        self._post()
        self._post('/2010/08/my-post')
        self._post('/2010/08/my-post')
        response = self.app.get('/blog/2010/08/my-post/history')
        assert 'My Post' in response
        # two revisions are shown
        assert '2 by Test Admin' in response
        assert '1 by Test Admin' in response

    def test_post_diff(self):
        self._post()
        self._post('/2010/08/my-post', text='sometext')
        self.app.post('/blog/2010/08/my-post/revert', params=dict(version='1'))
        response = self.app.get('/blog/2010/08/my-post/')
        response = self.app.get('/blog/2010/08/my-post/diff?v1=0&v2=0')
        assert 'My Post' in response
