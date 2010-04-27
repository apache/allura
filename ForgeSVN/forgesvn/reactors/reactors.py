import errno, logging, os, stat, subprocess

from pylons import c

from pyforge.lib.decorators import audit, react

log = logging.getLogger(__name__)

@audit('scm.svn.init')
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
    log.info('svnadmin create '+repo_path+repo_name)
    result = subprocess.call(['svnadmin', 'create', repo_name],
                             cwd=repo_path)
    magic_file = repo_path + repo_name + '/.SOURCEFORGE-REPOSITORY'
    with open(magic_file, 'w') as f:
        f.write('svn')
    os.chmod(magic_file, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
    repo.status = 'ready'
