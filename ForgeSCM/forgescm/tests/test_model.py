import os
from unittest import TestCase
from pylons import c, g
import ming
from pyforge import model as M
from pyforge.lib import app_globals
from forgescm.lib import hg, git
import sys
from forgescm import model as FM
from forgescm.tests import TestController
from nose.tools import assert_true
from forgescm.tests import test_helper

ming.configure(**{'ming.main.master':'mongo://localhost:27017/pyforge'})

class EmptyClass(object): pass

class TestRepository(TestCase):
    new_fork_mount_point = "new_fork"

    def setUp(self):
        test_helper.test_setup_app()
        test_helper.ensure_c_project_and_app()

    # pedantic; testing a test
    def test_create_git_repo(self):
        result = test_helper.create_git_repo()
        assert "commit" in result.output

    def test_fork(self):
        test_helper.create_git_repo()
        test_helper.clone_git_repo(c.app.repo)
        c.user = M.User.query.get(username='test_admin')
        c.app.repo.fork(c.project._id, self.new_fork_mount_point)

        # 1. assert that a new mount point is created
        assert_true(c.project.app_instance(self.new_fork_mount_point))
        # 2. assert that the message was published
        # NYI

    def test_hg_init(self):
        repo = c.app.repo
        repo.type = "hg"
        repo.init(dict())
        assert repo.status == 'Ready'

        # assert web is setup - NYI

        # assert commit hook is setup
        commit_hook_path = os.path.join(repo.repo_dir,'.hg', 'hgrc')
        assert os.path.isfile(commit_hook_path)

    def test_svn_init(self):
        repo = c.app.repo
        repo.type = "svn"
        repo.init(dict())
        assert repo.status == 'Ready'
        # assert web is setup
        # assert commit hook is setup

    def test_git_init(self):
        repo = c.app.repo
        repo.type = "git"
        readme_path = test_helper.create_readme(repo.repo_dir) # creates a file named README in repo_dir
        repo.init(dict())

        # the readme we created above should be gone
        assert os.path.isfile(readme_path) == False
        assert repo.status == 'Ready'

        # assert web is setup
        gitweb_conf_path = os.path.join(repo.repo_dir, 'gitweb.conf')
        assert os.path.isfile(gitweb_conf_path)

        # assert commit hook is setup
        commit_hook_path = os.path.join(repo.repo_dir,'.git', 'hooks', 'post-receive')
        assert os.path.isfile(commit_hook_path)

    # this is incomplete, should also have tests
    # for each public method in Repository, Commit, Patch

class TestCommit(TestCase):
    def setUp(self):
        return
