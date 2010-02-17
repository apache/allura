import os
import sys
import logging
import shutil
from forgescm.lib import hg, git
from pylons import c, g
from tg import config
from paste.deploy import loadapp
from pyforge import model as M
from paste.script.appinstall import SetupCommand
from webtest import TestApp
from time import sleep
from pyforge.lib import app_globals
from forgescm.lib import git

from forgescm.lib.command import Command
log = logging.getLogger(__name__)

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
    test_config = os.environ.get('SANDBOX') and 'sandbox-test.ini' or 'test.ini'

    # Loading the application:
    conf_dir = config.here = os.path.abspath(
        os.path.dirname(__file__) + '/../..')
    wsgiapp = loadapp('config:%s#main' % test_config, relative_to=conf_dir)
    app = TestApp(wsgiapp)

    # Setting it up:
    test_file = os.path.join(conf_dir, test_config)
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])
    return app

def ensure_c_project_and_app():
    g._push_object(app_globals.Globals())
    c._push_object(EmptyClass())
    get_project = lambda: M.Project.query.get(shortname='test')
    while get_project() is None:
      sleep(0.1)
    c.project = get_project()
    c.app = c.project.app_instance('src')

# used by test_fork
def setup_simple_git_repo(repo):
    url = create_git_repo()
    return clone_git_repo(repo, url)


def test_svn_repo_dir():
    return os.path.join(os.path.dirname(__file__), 'svn_repo')

def test_hg_repo_dir():
    return os.path.join(os.path.dirname(__file__), 'hg_repo')

def setup_simple_hg_repo(repo):
    src = test_hg_repo_dir()
    if os.path.exists(repo.repo_dir):
      shutil.rmtree(repo.repo_dir)
    shutil.copytree(src, repo.repo_dir)
    assert "changeset" in repo.scmlib().scm_log().run().output

# creates an empty git repo, and then adds one commit to it
def create_git_repo():
    tgz = os.path.join(os.path.dirname(__file__), 'git_repo.tgz')
    dest = "/tmp/git_repo"
    os.system("tar zvfx %s --directory %s &> /dev/null" % (tgz, os.path.dirname(dest)))
    return dest

def clone_git_repo(repo, url):
    repo.type = "git"
    repo.app.config.options.type = "git"

    # following is copied from reactors/git_react.py,
    # should be factored out
    repo.clear_commits()
    cmd = git.clone(url, 'git_dest')
    cmd.clean_dir()
    repo.clear_commits()
    cmd.run()

    log.info('Clone complete for %s', url)
    repo_name = c.project.shortname + c.app.config.options.mount_point
    git.setup_gitweb(repo_name, repo.repo_dir)
    git.setup_commit_hook(repo.repo_dir, c.app.config.script_name()[1:])
    if cmd.sp.returncode:
        errmsg = cmd.output
        g.publish('react', 'error', dict(
                message=errmsg))
        repo.status = 'Error: %s' % errmsg
    else:
        g.publish('react', 'scm.cloned', dict(
                url=url))
    return cmd.cwd()
