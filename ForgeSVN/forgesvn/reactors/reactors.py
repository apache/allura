import errno, logging, os, stat, subprocess

from pylons import c

from allura.lib.decorators import audit, react

from allura import model as M

log = logging.getLogger(__name__)

@audit('scm.svn.init')
def init(routing_key, data):
    repo = c.app.repo
    repo.init()
    M.Notification.post_user(
        c.user, repo, 'created',
        text='SVN repository created')
