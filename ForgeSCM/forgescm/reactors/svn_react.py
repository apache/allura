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
    # svn init
    log.info('SVN init')
    repo = c.app.repo
    repo.type = 'svn'
    repo.clear_commits()
    repo.parent = None
    cmd = svn.init()
    cmd.clean_dir()
    try:
        cmd.run_exc()
        svn.setup_commit_hook(repo.repo_dir, c.app.config.script_name()[1:])
        hg.clone('file://%s/svn' % cmd.cwd(), 'hg_repo').run_exc()
    except AssertionError, ae:
        g.publish('react', 'error', dict(
                message=ae.args[0]))
        repo.status = 'Error: %s' % ae.args[0]
    except Exception, ex:
        g.publish('react', 'error', dict(message=str(ex)))
        repo.status = 'Error: %s' % ex
    repo.status = 'Ready'

@audit('scm.svn.clone')
def clone(routing_key, data):
    repo = c.app.repo
    log.info('Begin cloning %s', data['url'])
    repo.type = 'svn'
    repo.clear_commits()
    # Perform the clone
    try:
        svn.svn_clone(data['url'])
        svn.setup_commit_hook(repo.repo_dir, c.app.config.script_name()[1:])
        log.info('Clone complete for %s', data['url'])
        g.publish('react', 'scm.cloned', dict(
                url=data['url']))
    except AssertionError, ae:
        g.publish('react', 'error', dict(
                message=ae.args[0]))
        repo.status = 'Error: %s' % ae.args[0]
    except Exception, ex:
        g.publish('react', 'error', dict(message=str(ex)))
        repo.status = 'Error: %s' % ex

@audit('scm.svn.fork')
def fork(routing_key, data):
    log.info('Begin forking %s => %s', data['forked_from'], data['forked_to'])
    set_context(**encode_keys(data['forked_to']))
    # Set repo metadata
    repo = c.app.repo
    repo.forked_from.update(data['forked_from'])
    # Perform the clone
    log.info('Cloning from %s', data['url'])
    try:
        svn.svn_clone(data['url'])
        repo.status = 'Ready'
        log.info('Clone complete for %s', data['url'])
        log.info("Sending scm.forked message")
        g.publish('react', 'scm.forked', data)
    except AssertionError, ae:
        g.publish('react', 'error', dict(
                message=ae.args[0]))
        repo.status = 'Error: %s' % ae.args[0]
    except Exception, ex:
        g.publish('react', 'error', dict(message=str(ex)))
        repo.status = 'Error: %s' % ex

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

