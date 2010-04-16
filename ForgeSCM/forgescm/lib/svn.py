import os
import sys
import logging

import pylons
import pkg_resources
from pymongo import bson

from forgescm import model as M
from .command import Command
from . import hg
from pyforge.lib.helpers import render_genshi_plaintext

log = logging.getLogger(__name__)

class init(Command):
    base='svnadmin create .'

class sync(Command):
    base = 'svnsync'

class rebase(Command):
    base='hg rebase --svn'

    def cwd(self):
        return Command.cwd(self) + '/hg_repo'

def svn_clone(remote):
    '''Clone one svn repo using svnsync'''
    # Create the svn repo
    cmd = init()
    cmd.clean_dir()
    cmd.run_exc()
    # Allow svnsync to change revprops
    revprop_hook = os.path.join(
        cmd.cwd(),
        './hooks/pre-revprop-change')
    # os.remove(revprop_hook)
    os.symlink('/bin/true', revprop_hook)
    # Use svnsync to clone svn=>svn
    sync('init', 'file://%s' % cmd.cwd(), 'file://%s' % remote).run_exc()
    sync('sync', 'file://%s' % cmd.cwd()).run_exc()

def setup_scmweb(self, repo_dir):
    return

def setup_commit_hook(repo_dir, plugin_id):
    'Set up the svn post-commit hook'
    tpl_fn = pkg_resources.resource_filename(
        'forgescm', 'data/svn/post-commit_tmpl')
    text = render_genshi_plaintext(tpl_fn, 
        executable=sys.executable,
        repository=plugin_id,
        config=pylons.config['__file__'])
    fn = os.path.join(repo_dir, 'hooks/post-commit')
    with open(fn, 'w') as fp:
        fp.write(text)
    os.chmod(fn, 0755)

