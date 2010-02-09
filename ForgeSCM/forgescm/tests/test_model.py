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
from pyforge.lib.helpers import push_config, set_context, encode_keys
from nose.tools import assert_equal

ming.configure(**{'ming.main.master':'mongo://localhost:27017/pyforge'})

class EmptyClass(object): pass

class TestRepository(TestCase):
    new_fork_mount_point = "new_fork"

    def setUp(self):
        test_helper.test_setup_app()
        test_helper.ensure_c_project_and_app()

    def test_git_do_fork(self):
        # setup a git repo with code
        repo = c.app.repo
        clone_url = test_helper.setup_simple_git_repo(repo)
        assert repo.type == "git"
        # fork it
        #   need: src_project, src_url, src_app
        clone_url = repo.clone_url()
        p = c.app.project

        # need a user to fork
        c.user = M.User.query.get(username='test_admin')
        app = p.install_app('Repository',
                "test_git_fork",
                type="git")
        with push_config(c, project=p, app=app):
            repo = app.repo
            repo.type = app.repo.type
            repo.status = 'pending fork'
            new_url = repo.url()
        c.app.repo.do_fork(dict(
                url=clone_url,
                forked_to=dict(project_id=str(p._id),
                               app_config_id=str(app.config._id)),
                forked_from=dict(project_id=str(c.project._id),
                                 app_config_id=str(c.app.config._id))))

        # verify fork
        assert app.repo.repo_dir
        assert app.repo.scmlib() == git
        assert "commit" in app.repo.scmlib().scm_log().run().output

    def test_hg_do_fork(self):
        repo = c.app.repo
        # setup an hg repo with code
        test_helper.setup_simple_hg_repo(repo)
        assert repo.type == "hg"

        # fork it
        #   need: src_project, src_url, src_app
        clone_url = repo.repo_dir # was repo.clone_url() but should use local, filesystem address
        p = c.app.project

        # need a user to fork
        c.user = M.User.query.get(username='test_admin')
        app = p.install_app('Repository',
                "test_hg_fork",
                type="hg")
        with push_config(c, project=p, app=app):
            repo = app.repo
            repo.type = app.repo.type
            repo.status = 'pending fork'
            new_url = repo.url()
        c.app.repo.do_fork(dict(
                url=clone_url,
                forked_to=dict(project_id=str(p._id),
                               app_config_id=str(app.config._id)),
                forked_from=dict(project_id=str(c.project._id),
                                 app_config_id=str(c.app.config._id))))

        # verify fork
        assert app.repo.repo_dir
        assert app.repo.scmlib() == hg
        assert "changeset" in app.repo.scmlib().scm_log().run().output

    def test_setup_simple_git_repo(self):
        repo = c.app.repo
        url = test_helper.create_git_repo()
        test_helper.setup_simple_git_repo(repo)

    def test_fork(self):
        c.user = M.User.query.get(username='test_admin')
        c.app.repo.fork(c.project._id, self.new_fork_mount_point)

        # 1. assert that a new mount point is created
        assert_true(c.project.app_instance(self.new_fork_mount_point))

    def test_hg_init(self):
        repo = c.app.repo
        repo.do_init(dict(), "hg")
        assert repo.status == 'Ready'
        assert_equal(repo.type, "hg")

        # assert web is setup - NYI

        # assert commit hook is setup
        commit_hook_path = os.path.join(repo.repo_dir,'.hg', 'hgrc')
        assert os.path.isfile(commit_hook_path)
        assert "python:forgescm.lib.hg.incoming_hook" in open(commit_hook_path, "r").read()
        repo.scmlib().scm_log().run_exc()

    def test_svn_init(self):
        repo = c.app.repo
        repo.do_init(dict(), "svn")
        assert_equal(repo.type, "svn")
        assert repo.status == 'Ready'
        # assert web is setup
        # assert commit hook is setup
        assert os.path.isfile(os.path.join(repo.repo_dir, "hooks/post-commit"))

    def test_git_init(self):
        repo = c.app.repo
        readme_path = test_helper.create_readme(repo.repo_dir) # creates a file named README in repo_dir
        repo.do_init(dict(), "git")
        assert_equal(repo.type, "git")

        # the readme we created above should be gone
        assert os.path.isfile(readme_path) == False
        assert repo.status == 'Ready'

        # assert web is setup
        gitweb_conf_path = os.path.join(repo.repo_dir, 'gitweb.conf')
        assert os.path.isfile(gitweb_conf_path)

        # assert commit hook is setup
        commit_hook_path = os.path.join(repo.repo_dir,'.git', 'hooks', 'post-receive')
        assert os.path.isfile(commit_hook_path)

    def test_create_git_repo(self):
        url = test_helper.create_git_repo()
        assert "git_repo" in url
        assert os.path.exists(url + "/.git")

    def test_git_clone(self): # clone is how we copy from an external repo to OpenForge
        repo = c.app.repo
        src_url = test_helper.create_git_repo()
        repo.do_clone(src_url, "git")

        assert_equal(repo.cloned_from, src_url)
        assert src_url != repo.repo_dir
        assert os.path.isdir(os.path.join(repo.repo_dir, ".git"))

    def test_hg_clone(self):
        repo = c.app.repo
        src_url = test_helper.test_hg_repo_dir()
        repo.do_clone(src_url, "hg")
        assert_equal(repo.cloned_from, src_url)
        assert src_url != repo.repo_dir
        assert os.path.isdir(os.path.join(repo.repo_dir, ".hg"))

    def test_svn_clone(self):
        repo = c.app.repo
        src_url = test_helper.test_svn_repo_dir()
        repo.do_clone(src_url, "svn")
        assert_equal(repo.cloned_from, src_url)
        assert src_url != repo.repo_dir
        assert os.path.isfile(os.path.join(repo.repo_dir, "conf", "svnserve.conf"))

class TestCommit(TestCase):
    def setUp(self):
        return
