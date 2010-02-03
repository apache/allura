import os
from unittest import TestCase
from pylons import c, g
import ming
from pyforge import model as M
from pyforge.lib import app_globals
from forgescm.reactors import common_react
from forgescm.reactors import git_react
import forgescm.reactors
from forgescm.tests import test_helper

ming.configure(**{'ming.main.master':'mongo://localhost:27017/pyforge'})

class EmptyClass(object): pass

class TestReact(TestCase):

    def setUp(self):
        test_helper.test_setup_app()
        test_helper.ensure_c_project_and_app()

    def publish(self, func, routing_key, data=None):
        if data is None: data = {}
        d = dict(data)
        d.update(project_id=c.project._id,
                 mount_point=c.app.config.options.mount_point)
        return func(routing_key, d)

    def test_initialized(self): # if I call this test_initialized, it fails in test_setup_app
        self.publish(common_react.initialized, 'scm.initialized')
        # incomplete, we need to validate result

    def test_forked_update(self):
        return # incomplete tests removed, see git history

    def test_cloned(self):
        self.publish(common_react.cloned, 'scm.cloned', dict(
                url='forgescm/tests/hg_repo'))

    #for_each (git, hg, svn):
    #    setup: create repo
    #    for_each (clone, fork, init, "reclone? why not kill this?", refresh_commit (what is it?)):
    #        test react
    #
    # But first, let's test the git_clone

    def test_git_fork(self):
        result = test_helper.create_git_repo()
        assert "commit" in result.output

        c.app.repo.type = "git"

        from_project = c.project
        to_project = c.project
        c.user = M.User.query.get(username='test_admin')
        to_app = to_project.install_app(
                'Repository',
                'new_mount_point',
                type=c.app.config.options.type)
        data = dict(
                url=c.app.repo.clone_url(),
                forked_to=dict(project_id=str(to_project._id),
                               app_config_id=str(to_app.config._id)),
                forked_from=dict(project_id=str(from_project._id),
                               app_config_id=str(c.app.config._id)))

        self.publish(git_react.fork, 'scm.git.fork', data)
        # missing: check that it was forked
