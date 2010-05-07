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
        text='Repository %s created' % repo.name)
