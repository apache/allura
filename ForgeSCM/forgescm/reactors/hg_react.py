import logging
from cStringIO import StringIO

from pylons import c, g
from pymongo import bson

from pyforge.lib.decorators import audit, react
from pyforge.lib.helpers import push_context, set_context, encode_keys
from pyforge.model import Project

from forgescm.lib import hg
from forgescm import model as M

log = logging.getLogger(__name__)

## Auditors
@audit('scm.hg.init')
def init(routing_key, data):
    repo = c.app.repo
    repo.type = 'hg'
    cmd = hg.init()
    cmd.clean_dir()
    repo.clear_commits()
    repo.parent = None
    cmd.run()
    if cmd.sp.returncode:
        g.publish('react', 'error', dict(
                message=cmd.output))
        repo.status = 'Error: %s' % cmd.output
        repo.m.save()
    else:
        repo.status = 'Ready'
        repo.m.save()

@audit('scm.hg.clone')
def clone(routing_key, data):
    repo = c.app.repo
    log.info('Begin cloning %s', data['url'])
    repo.type = 'hg'
    # Perform the clone
    cmd = hg.clone(data['url'], '.')
    cmd.clean_dir()
    cmd.run()
    log.info('Clone complete for %s', data['url'])
    if cmd.sp.returncode:
        errmsg = cmd.output
        g.publish('react', 'error', dict(
                message=errmsg))
        repo.status = 'Error: %s' % errmsg
        repo.m.save()
    else:
        g.publish('react', 'scm.cloned', dict(
                url=data['url']))

@audit('scm.hg.fork')
def fork(routing_key, data):
    log.info('Begin forking %s => %s', data['forked_from'], data['forked_to'])
    set_context(**encode_keys(data['forked_to']))
    # Set repo metadata
    repo = c.app.repo
    repo.type = 'hg'
    repo.forked_from.update(data['forked_from'])
    repo.m.save()
    # Perform the clone
    log.info('Cloning from %s', data['url'])
    cmd = hg.clone(data['url'], '.')
    cmd.clean_dir()
    cmd.run()
    repo.status = 'Ready'
    repo.m.save()
    log.info('Clone complete for %s', data['url'])
    if cmd.sp.returncode:
        errmsg = cmd.output
        g.publish('react', 'error', dict(
                message=errmsg))
        repo.status = 'Error: %s' % errmsg
        repo.m.save()
        return
    else:
        log.info("Sending scm.forked message")
        g.publish('react', 'scm.forked', data)

@audit('scm.hg.reclone')
def reclone(routing_key, data):
    set_context(data['project_id'], data['mount_point'])
    repo = c.app.repo
    # Perform the clone
    cmd = hg.clone(repo.parent, '.')
    cmd.clean_dir()
    cmd.run()
    if cmd.sp.returncode:
        g.publish('react', 'error', dict(
                message=cmd.sp.stdout.read()))
        return
    # Load the log
    cmd = hg.log('-g', '-p')
    cmd.run()
    # Clear the old set of commits
    repo.clear_commits()
    parser = hg.LogParser(repo._id)
    parser.feed(StringIO(cmd.output))
    # Update the repo status
    repo.status = 'Ready'
    repo.m.save()

## Reactors
@react('scm.hg.refresh_commit')
def refresh_commit(routing_key, data):
    set_context(data['project_id'], data['mount_point'])
    repo = c.app.repo
    hash = data['hash']
    log.info('Refresh commit %s', hash)
    # Load the log
    cmd = hg.scm_log('-g', '-p', '-r', hash)
    cmd.run()
    parser = hg.LogParser(repo._id)
    parser.feed(StringIO(cmd.output))

