import os
from unittest import TestCase
from pylons import c, g
import ming
from pyforge import model as M
from pyforge.lib import app_globals
from forgescm.lib import hg, git
from forgescm import model as FM

ming.configure(**{'ming.main.master':'mongo://localhost:27017/pyforge'})

class EmptyClass(object): pass

class TestCommand(TestCase):

    def setUp(self):
        g._push_object(app_globals.Globals())
        c._push_object(EmptyClass())
        c.project = M.Project.m.get(_id='projects/test/')
        c.app = c.project.app_instance('src')

    def test_init_log(self):
        cmd = hg.init()
        assert os.getcwd() != cmd.cwd()
        cmd.clean_dir()
        cmd.run()
        git.init().run()
        hg.scm_log('-g', '-p').run()
        git.scm_log('-p').run(output_consumer=lambda line:None)
        
    def test_setup_gitweb(self):
        repo = c.app.repo
        repo_name = c.project._id + c.app.config.options.mount_point
        git.setup_gitweb(repo_name, repo.repo_dir)
