import logging
from cStringIO import StringIO

from pylons import c, g
from pymongo import bson

from pyforge.lib.decorators import audit, react
from pyforge.lib.helpers import push_context, set_context, encode_keys
from pyforge.model import Project

from forgescm.lib import git
from pyforge import model as M
import sys

log = logging.getLogger(__name__)

## Auditors
@audit('scm.git.init')
def init(routing_key, data):
    repo = c.app.repo
    return repo.do_init(data, "git")

@audit('scm.git.clone')
def clone(routing_key, data):
    repo = c.app.repo
    return repo.do_clone(data['url'], "git")

@audit('scm.git.fork')
def fork(routing_key, data):
    # get from info
    src_project = M.Project.query.get(_id=bson.ObjectId(data['forked_from']['project_id']))
    src_app_config = M.AppConfig.query.get(_id=bson.ObjectId(data['forked_from']['app_config_id']))
    src_app = src_project.app_instance(src_app_config)

    assert src_app.repo.type == "git"
    return src_app.repo.do_fork(data)

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
