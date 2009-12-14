from urllib import urlencode

from tg import config
from nose.tools import assert_true

from forgescm.tests import TestController

class TestRootController(TestController):

    def test_index(self):
        response = self.app.get('/Repository/')
        assert_true('Welcome to ForgeSCM' in response)
        
    def test_fork(self):
        response = self.app.get(
            '/Repository/fork?',
            urlencode(dict(project='projects/test/',
                           mount_point='fork1')))
        assert_true(response.status_int == 302)

    def test_search(self):
        response = self.app.get(
            '/Repository/search')
        response = self.app.get(
            '/Repository/search?',
            urlencode(dict(q='as;ldjfa;lmseivals;evjalse',
                           history='false')))
        assert_true('No results.' in response, response)
        
    def test_reinit(self):
        response = self.app.get(
            '/Repository/reinit')
        assert_true(response.status_int == 302)
        
    def test_reclone(self):
        response = self.app.get(
            '/Repository/reclone')
        assert_true(response.status_int == 302)
        
    def test_clone_from(self):
        url = config.here + '/forgescm/tests/hg_repo'
        response = self.app.get(
            '/Repository/clone_from?',
            urlencode(dict(url=url)))
        assert_true(response.status_int == 302)
        
