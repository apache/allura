import os
import sys
from forgescm.lib import hg, git
from pylons import c, g
from tg import config
from paste.deploy import loadapp
from pyforge import model as M
from paste.script.appinstall import SetupCommand
from webtest import TestApp
from time import sleep
from pyforge.lib import app_globals

from forgescm.lib.command import Command

class git_add_all(Command):
    base='git add .'

class git_commit_all(Command):
    base='git commit -a -m "foo"'

def create_readme(dir):
    fn = os.path.join(dir, 'README')
    with open(fn, 'w') as fp:
        fp.write("Nothing to read, really\n")
    return fn

class EmptyClass(object): pass

def test_setup_app():
    """Method called by nose before running each test"""
    # Loading the application:
    conf_dir = config.here = os.path.abspath(
        os.path.dirname(__file__) + '/../..')
    wsgiapp = loadapp('config:test.ini#main', relative_to=conf_dir)
    app = TestApp(wsgiapp)

    # Setting it up:
    test_file = os.path.join(conf_dir, 'test.ini')
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])
    hg_repo_url = config.here + '/forgescm/tests/hg_repo'
    if not os.path.exists(hg_repo_url):
        system('hg init %s' % hg_repo_url)
    return app

def ensure_c_project_and_app():
    g._push_object(app_globals.Globals())
    c._push_object(EmptyClass())
    get_project = lambda: M.Project.query.get(shortname='test')
    while get_project() is None:
      sleep(0.1)
    c.project = get_project()
    c.app = c.project.app_instance('src')

def create_git_repo():
    save_dir = os.getcwd()
    os.chdir("/tmp")
    cmd = git.init()
    cmd.clean_dir()
    cmd.run()
    create_readme(c.app.repo.repo_dir)
    git_add_all().run()
    git_commit_all().run()
    log = git.scm_log()
    log.run()
    os.chdir(save_dir)
    return log

def clone_git_repo(repo):
    repo.type = "git"
    # following is copied from  reactors/git_react.py,
    # should be factored out
    repo.clear_commits()

