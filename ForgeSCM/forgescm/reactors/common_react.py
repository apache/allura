import logging

from pylons import c, g

from pyforge.lib.decorators import audit, react
from pyforge.lib.helpers import push_context, set_context, encode_keys
from forgescm.lib import hg

from forgescm import model as M

log = logging.getLogger(__name__)


@react('scm.initialized')
def initialized(routing_key, data):
    set_context(data['project_id'], data['mount_point'])
    repo = c.app.repo
    log.info('Setting repo status for %s', repo)
    repo.status = 'Ready'
    repo.m.save()
        
@react('scm.forked')
def forked_update_source(routing_key, data):
    log.info('Updating the source of a fork (%s)', data['forked_from'])
    set_context(**encode_keys(data['forked_from']))
    repo = c.app.repo
    repo.forks.append(data['forked_to'])
    repo.m.save()

@react('scm.forked')
def forked_update_dest(routing_key, data):
    log.info('Updating the dest of a fork', data['forked_to'])
    set_context(**encode_keys(data['forked_to']))
    # Update dest repo
    repo = c.app.repo
    repo.forked_from.update(data['forked_from'])
    repo.clear_commits()
    repo.m.save()
    # Copy history from source
    commit_extra = dict(
        app_config_id = c.app.config._id,
        repository_id = repo._id)
    # Copy the history
    log.info('Begin history copy')
    with push_context(**repo.forked_from):
        parent_repo = c.app.repo
        for commit in parent_repo.commits():
            patches = commit.patches
            with push_context(**encode_keys(data['forked_to'])):
                commit = M.Commit.make(commit)
                commit.update(commit_extra)
                commit.m.save()
                for p in patches:
                    p.update(commit_extra)
                    p.commit_id = commit._id
                    M.Patch.make(p).m.save()
    log.info('History copy complete')

@react('scm.cloned')
def cloned(routing_key, data):
    set_context(data['project_id'], data['mount_point'])
    repo = c.app.repo
    # Update the repo status
    repo.status = 'Ready'
    repo.parent = data['url']
    repo.m.save()
    assert c.app.config.options.type == 'hg'
    # Load the log & create refresh commit messages
    log.info('Begin log %s', data['url'])
    type = c.app.config.options['type']
    if type == 'hg':
        cmd = hg.scm_log('-g', '-p')
        parser = hg.LogParser(repo._id)
        cmd.run(output_consumer=parser.feed)
    else:
        log.warning('Cannot index repos of type %s', type)
    log.info('Log complete %s', data['url'])

