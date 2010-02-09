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
    return repo.do_init(data, "hg")

@audit('scm.hg.clone')
def clone(routing_key, data):
    repo = c.app.repo
    return repo.do_clone(data['url'], "hg")

@audit('scm.hg.fork')
def fork(routing_key, data):
    src_project = M.Project.query.get(_id=bson.ObjectId(data['forked_from']['project_id']))
    src_app_config = M.AppConfig.query.get(_id=bson.ObjectId(data['forked_from']['app_config_id']))
    src_app = src_project.app_instance(src_app_config)

    assert src_app.repo.type == "hg"
    return src_app.repo.do_fork(data)

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
    hg.setup_commit_hook(repo.repo_dir, c.app.config.script_name()[1:])
    repo.status = 'Ready'

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

