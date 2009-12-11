import logging
from cStringIO import StringIO

from pylons import c, g

from pyforge.lib.decorators import audit
from pyforge.lib.helpers import push_config

from forgescm.lib import hg
from forgescm import model as M

log = logging.getLogger(__name__)

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
    else:
        log.info('Setting repo status for %s', repo)
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
        return
    # Update the repo status
    repo.status = 'Ready'
    repo.parent = data['url']
    repo.clear_commits()
    repo.m.save()
    # Load the log & create refresh commit messages
    log.info('Begin log %s', data['url'])
    cmd = hg.scm_log('-g', '-p')
    parser = hg.LogParser(repo._id)
    cmd.run(output_consumer=parser.feed)
    log.info('Log complete %s', data['url'])

@audit('scm.hg.fork')
def fork(routing_key, data):
    repo = c.app.repo
    log.info('Begin forking')
    repo.type = 'hg'
    # Perform the clone
    with repo.context_of(repo.forked_from) as parent_repo:
        clone_url = repo.clone_url()
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
        return
    # Update the repo status
    repo.status = 'Ready'
    repo.parent = data['url']
    repo.clear_commits()
    repo.m.save()
    my_context = dict(project=c.project, app=c.app)
    commit_extra = dict(
        app_config_id = c.app.config._id,
        repository_id = repo._id)
    # Copy the history
    log.info('Begin history copy')
    with repo.context_of(repo.forked_from) as parent_repo:
        for commit in parent_repo.commits():
            patches = commit.patches
            with push_config(c, **my_context):
                commit = M.Commit.make(commit)
                commit.update(commit_extra)
                commit.m.save()
                log.info('Commit repo ID is %s', commit.repository_id)
                log.info('Repo id is %s', repo._id)
                for p in patches:
                    p.update(commit_extra)
                    p.commit_id = commit._id
                    M.Patch.make(p).m.save()
    log.info('History copy complete')

@audit('scm.hg.refresh_commit')
def refresh_commit(routing_key, data):
    repo = c.app.repo
    hash = data['hash']
    log.info('Refresh commit %s', hash)
    # Load the log
    cmd = hg.scm_log('-g', '-p', '-r', hash)
    cmd.run()
    parser = hg.LogParser(repo._id)
    parser.feed(StringIO(cmd.output))

@audit('scm.hg.reclone')
def reclone(routing_key, data):
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

