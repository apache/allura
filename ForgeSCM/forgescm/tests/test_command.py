import os
from unittest import TestCase
from pylons import c, g
import ming
from pyforge import model as M
from pyforge.lib import app_globals
from forgescm.lib import hg, git
from forgescm import model as FM
from forgescm.tests import test_helper
from time import sleep


ming.configure(**{'ming.main.master':'mongo://localhost:27017/pyforge'})

class EmptyClass(object): pass

class TestCommand(TestCase):

    def setUp(self):
        test_helper.test_setup_app()
        test_helper.ensure_c_project_and_app()

    def test_init_hg_log(self):
        cmd = hg.init()
        assert os.getcwd() != cmd.cwd()
        cmd.clean_dir()
        cmd.run()
        hg.scm_log('-g', '-p').run()
        
    def test_init_git_log(self):
        cmd = git.init()
        assert os.getcwd() != cmd.cwd()
        cmd.clean_dir()
        cmd.run()
        assert os.path.exists(os.path.join(cmd.cwd(), ".git"))

    def test_setup_gitweb(self):
        repo = c.app.repo
        repo_name = c.project.shortname + c.app.config.options.mount_point
        git.setup_gitweb(repo_name, repo.repo_dir)
