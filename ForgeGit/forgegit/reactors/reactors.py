import os
import sys
import stat
import errno
import logging
import subprocess

import pkg_resources
import pylons

from pyforge.lib.decorators import audit, react
from pyforge import model as M
from pyforge.lib import helpers as h

log = logging.getLogger(__name__)

@audit('scm.git.init')
def init(routing_key, data):
    repo = pylons.c.app.repo
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
    magic_file = os.path.join(fullname, '.SOURCEFORGE-REPOSITORY')
    with open(magic_file, 'w') as f:
        f.write('git')
    os.chmod(magic_file, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
    _setup_receive_hook(
        fullname,
        pylons.c.app.config.script_name())
    repo.status = 'ready'
    M.Notification.post_user(pylons.c.user, repo, 'created',
                             text='Repository %s created' % repo_name)

@react('scm.git.refresh_commit')
def refresh_commit(routing_key, data):
    h.set_context(data['project_id'], data['mount_point'])
    repo = pylons.c.app.repo
    hash = data['hash']
    log.info('Refresh commit %s', hash)

def _setup_receive_hook(repo_dir, plugin_id):
    'Set up the git post-commit hook'
    tpl_fn = pkg_resources.resource_filename(
        'forgegit', 'data/post-receive_tmpl')
    config = pylons.config.get('__file__')
    text = h.render_genshi_plaintext(tpl_fn, 
        executable=sys.executable,
        repository=plugin_id,
        config=config)
    fn = os.path.join(repo_dir, 'hooks', 'post-receive')
    with open(fn, 'w') as fp:
        fp.write(text)
    os.chmod(fn, 0755)

