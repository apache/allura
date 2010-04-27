import errno, logging, os, stat, subprocess

from pylons import c

from pyforge.lib.decorators import audit, react
from pyforge import model as M

log = logging.getLogger(__name__)

@audit('scm.hg.init')
def init(routing_key, data):
    repo = c.app.repo
    repo_name = data['repo_name']
    repo_path = data['repo_path']
    if not repo_path.endswith('/'): repo_path += '/'
    try:
        os.makedirs(repo_path)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise
    # We may eventually require --template=...
    log.info('hg init '+repo_path+repo_name)
    result = subprocess.call(['hg', 'init', repo_name],
                             cwd=repo_path)
    magic_file = repo_path + repo_name + '/.SOURCEFORGE-REPOSITORY'
    with open(magic_file, 'w') as f:
        f.write('hg')
    os.chmod(magic_file, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
    repo.status = 'ready'
    M.Notification.post_user(c.user, repo, 'created',
                             text='Repository %s created' % repo_name)
