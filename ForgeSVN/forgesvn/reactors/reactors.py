import errno, logging, os, stat, subprocess

from pylons import c

from pyforge.lib.decorators import audit, react

from pyforge import model as M

log = logging.getLogger(__name__)

@audit('scm.svn.init')
def init(routing_key, data):
    repo = c.app.repo
    repo.init()
    M.Notification.post_user(
        c.user, repo, 'created',
        text='Repository %s created' % repo.name)
