import logging

import pylons

from pyforge.lib.decorators import audit, react
from pyforge import model as M
from pyforge.lib import helpers as h
from pyforge.lib import search

log = logging.getLogger(__name__)

@audit('scm.git.init')
def init(routing_key, data):
    repo = pylons.c.app.repo
    repo.init()
    M.Notification.post_user(
        pylons.c.user, repo, 'created',
        text='Git repository created')

@audit('scm.git.clone')
def clone(routing_key, data):
    repo = pylons.c.app.repo
    repo.init_as_clone(data['cloned_from'])
    M.Notification.post_user(
        pylons.c.user, repo, 'created',
        text='Git repository created')

@react('scm.git.refresh_commit')
def refresh_commit(routing_key, data):
    repo = pylons.c.app.repo
    hash = data['hash']
    log.info('Refresh commit %s', hash)
    c_from, c_to = hash.split('..')
    for cobj in repo.iter_commits(rev=hash):
        aref = cobj.dump_ref()
        for ref in search.find_shortlinks(cobj.message):
            M.ArtifactReference(ref.artifact_reference).to_artifact().backreferences['git_%s' % hash] = aref
