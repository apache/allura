'''
Subversion support is a little bit weird.  The approach used here is to
use the repo_dir as a base and have a svn repo checked out alongside an hg clone
of that svn repo:

$repo_dir
 |-svn_repo
 \-hg_repo

We will use the hgsubversion extension to clone svn=>hg and then use as
much as possible from the hg implementation after that.
'''
import logging
from cStringIO import StringIO

from pylons import c, g
from pymongo import bson

from pyforge.lib.decorators import audit, react
from pyforge.lib.helpers import push_context, set_context, encode_keys
from pyforge.model import Project

from forgescm.lib import svn, hg
from forgescm import model as M

log = logging.getLogger(__name__)

## Auditors
@audit('scm.svn.init')
def init(routing_key, data):
    log.info('SVN init')
    repo = c.app.repo
    return repo.do_init(data, "svn")

@audit('scm.svn.clone')
def clone(routing_key, data):
    repo = c.app.repo
    return repo.do_clone(data['url'], "svn")

@audit('scm.svn.fork')
def fork(routing_key, data):
    assert False # SVN forking is not supported

@audit('scm.svn.reclone')
def reclone(routing_key, data):
    set_context(data['project_id'], data['mount_point'])
    repo = c.app.repo
    repo.clear_commits()
    # Perform the clone
    try:
        svn.svn_clone(repo.parent)
        svn.setup_commit_hook(repo.repo_dir, c.app.config.script_name()[1:])
        g.publish('react', 'scm.cloned', dict(
                url=data['url']))
        repo.status = 'Ready'
    except AssertionError, ae:
        g.publish('react', 'error', dict(
                message=ae.args[0]))
        repo.status = 'Error: %s' % ae.args[0]
    except Exception, ex:
        g.publish('react', 'error', dict(message=str(ex)))
        repo.status = 'Error: %s' % ex

## Reactors
@react('scm.svn.refresh_commit')
def refresh_commit(routing_key, data):
    set_context(data['project_id'], data['mount_point'])
    repo = c.app.repo
    hash = data['hash']
    log.info('Refresh commit %s', hash)
    # Load the log
    try:
        svn.scm_rebase().run_exc()
        cmd = svn.scm_log('-g', '-p', '--debug', '-r', hash).run_exc()
        parser = hg.LogParser(repo._id)
        parser.feed(StringIO(cmd.output))
    except AssertionError, ae:
        g.publish('react', 'error', dict(
                message=ae.args[0]))
        repo.status = 'Error: %s' % ae.args[0]
    except Exception, ex:
        g.publish('react', 'error', dict(message=str(ex)))
        repo.status = 'Error: %s' % ex

@react('scm.svn.cloned')
def refresh_log(routing_key, data):
    set_context(data['project_id'], data['mount_point'])
    repo = c.app.repo
    repo.clear_commits()
    cmd = svn.scm_log('-g', '-p', '--debug')
    cmd.run()
    parser = hg.LogParser(repo._id)
    parser.feed(StringIO(cmd.output))

