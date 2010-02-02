import logging
from cStringIO import StringIO

from pylons import c, g
from pymongo import bson

from pyforge.lib.decorators import audit, react
from pyforge.lib.helpers import push_context, set_context, encode_keys
from pyforge.model import Project

from forgescm.lib import git
from forgescm import model as M

log = logging.getLogger(__name__)

## Auditors
@audit('scm.git.init')
def init(routing_key, data):
    log.info('GIT init')
    repo = c.app.repo
    repo.type = 'git'
    cmd = git.init()
    cmd.clean_dir()
    repo.clear_commits()
    repo.parent = None
    cmd.run()
    log.info('Setup gitweb in %s', repo.repo_dir)
    repo_name = c.project.shortname + c.app.config.options.mount_point
    git.setup_gitweb(repo_name, repo.repo_dir)
    git.setup_commit_hook(repo.repo_dir, c.app.config.script_name()[1:])
    if cmd.sp.returncode:
        g.publish('react', 'error', dict(
                message=cmd.output))
        repo.status = 'Error: %s' % cmd.output
    else:
        repo.status = 'Ready'

@audit('scm.git.clone')
def clone(routing_key, data):
    repo = c.app.repo
    log.info('Begin cloning %s', data['url'])
    repo.type = 'git'
    # Perform the clone
    cmd = git.clone(data['url'], '.')
    cmd.clean_dir()
    repo.clear_commits()
    cmd.run()
    log.info('Clone complete for %s', data['url'])
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
                url=data['url']))

@audit('scm.git.fork')
def fork(routing_key, data):
    log.info('Begin forking %s => %s', data['forked_from'], data['forked_to'])
    set_context(**encode_keys(data['forked_to']))
    # Set repo metadata
    repo = c.app.repo
    repo.type = 'git'
    repo.forked_from.update(data['forked_from'])
    # Perform the clone
    log.info('Cloning from %s', data['url'])
    cmd = git.clone(data['url'], '.')
    cmd.clean_dir()
    repo.clear_commits()
    cmd.run()
    repo.status = 'Ready'
    log.info('Clone complete for %s', data['url'])
    repo_name = c.project.shortname + c.app.config.options.mount_point
    git.setup_gitweb(repo_name, repo.repo_dir)
    git.setup_commit_hook(repo.repo_dir, c.app.config.script_name()[1:])
    if cmd.sp.returncode:
        errmsg = cmd.output
        g.publish('react', 'error', dict(
                message=errmsg))
        repo.status = 'Error: %s' % errmsg
        return
    else:
        log.info("Sending scm.forked message")
        g.publish('react', 'scm.forked', data)

@audit('scm.git.reclone')
def reclone(routing_key, data):
    set_context(data['project_id'], data['mount_point'])
    repo = c.app.repo
    # Perform the clone
    cmd = git.clone(repo.parent, '.')
    cmd.clean_dir()
    repo.clear_commits()
    cmd.run()
    if cmd.sp.returncode:
        g.publish('react', 'error', dict(
                message=cmd.sp.stdout.read()))
        return
    # Load the log
    cmd = git.scm_log('-p')
    cmd.run()
    # Clear the old set of commits
    repo.clear_commits()
    parser = git.LogParser(repo._id)
    parser.feed(StringIO(cmd.output))
    # Update the repo status
    repo.status = 'Ready'

## Reactors
@react('scm.git.refresh_commit')
def refresh_commit(routing_key, data):
    set_context(data['project_id'], data['mount_point'])
    repo = c.app.repo
    hash = data['hash']
    log.info('Refresh commit %s', hash)
    # Load the log
    if '..' in hash:
        cmd = git.scm_log('-p', hash)
    else:
        cmd = git.scm_log('-p', '-1', hash)
    parser = git.LogParser(repo._id)
    cmd.run(output_consumer=parser.feed)
