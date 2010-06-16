import logging

import pylons

from pyforge.lib.decorators import audit, react
from pyforge import model as M

log = logging.getLogger(__name__)

@audit('scm.hg.init')
def init(routing_key, data):
    repo = pylons.c.app.repo
    repo.init()
    M.Notification.post_user(
        pylons.c.user, repo, 'created',
        text='Hg repository created')

@audit('scm.hg.clone')
def clone(routing_key, data):
    repo = pylons.c.app.repo
    repo.init_as_clone(data['cloned_from'])
    M.Notification.post_user(
        pylons.c.user, repo, 'created',
        text='Hg repository created')
