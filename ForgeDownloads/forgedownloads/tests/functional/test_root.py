from nose.tools import assert_equals
from ming.orm import ThreadLocalORMSession

from allura import model as M
from alluratest.controller import TestController


class TestRootController(TestController):

    def test_root_redirect(self):
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        project = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        project.set_tool_data('sfx', unix_group_name='foobar')
        ThreadLocalORMSession.flush_all()

        response = self.app.get('/downloads/', status=301)
        assert_equals(response.location, 'http://localhost/projects/foobar/files/')

    def test_root(self):
        self.app.get('/downloads/', status=404)
