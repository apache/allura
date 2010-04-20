from urllib import urlencode

from tg import config
from nose.tools import assert_true

from forgescm.tests import TestController
from pyforge.model import Project
from forgescm.tests import test_helper
from pylons import c, g
import sys

class TestRootController(TestController):

    def test_index(self):
        test_helper.ensure_c_project_and_app()
        response = self.app.get('/Repository/')
        assert_true('Welcome to ForgeSCM' in response)

    def test_gitweb(self):
        test_helper.ensure_c_project_and_app()
        assert c.app
        response = self.app.get('/_wsgi_/scm/p/test/src_git/.git')
        assert response

        
    def test_fork(self):
        test_helper.ensure_c_project_and_app()
        project = c.project
        assert project
        response = self.app.get(
            '/Repository/fork?',
            urlencode(dict(project_id=project._id,
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
        test_helper.ensure_c_project_and_app()
        response = self.app.get('/Repository/reinit')
        assert_true(response.status_int == 302)
        
    def test_reclone(self):
        test_helper.ensure_c_project_and_app()
        response = self.app.get(
            '/Repository/reclone')
        assert_true(response.status_int == 302)
        
    def test_clone_from(self):
        url = config.here + '/forgescm/tests/hg_repo'
        response = self.app.get(
            '/Repository/clone_from?',
            urlencode(dict(url=url)))
        assert_true(response.status_int == 302)
        
