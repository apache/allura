import errno, logging, os, subprocess

from pylons import c

from pyforge.lib.decorators import audit, react

log = logging.getLogger(__name__)

@audit('scm.git.init')
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
    log.info('git init '+repo_path+repo_name)
    result = subprocess.call(['git', 'init', '--bare', '--shared=all', repo_name],
                             cwd=repo_path)
    repo.status = 'ready'
