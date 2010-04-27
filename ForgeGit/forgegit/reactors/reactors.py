import errno, logging, os, stat, subprocess

from pylons import c

from pyforge.lib.decorators import audit, react

log = logging.getLogger(__name__)

@audit('scm.git.init')
def init(routing_key, data):
    repo = c.app.repo
    repo_name = data['repo_name']
    repo_path = data['repo_path']
    fullname = os.path.join(repo_path, repo_name)
    try:
        os.makedirs(fullname)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise
    # We may eventually require --template=...
    log.info('git init %s', fullname)
    result = subprocess.call(['git', 'init', '--bare', '--shared=all'],
                             cwd=fullname)
    magic_file = repo_path + repo_name + '/.SOURCEFORGE-REPOSITORY'
    with open(magic_file, 'w') as f:
        f.write('git')
    os.chmod(magic_file, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
    repo.status = 'ready'
