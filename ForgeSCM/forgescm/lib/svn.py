import os
import sys
import logging

import genshi
import pylons
import pkg_resources
from pymongo import bson

from forgescm import model as M
from .command import Command
from . import hg

log = logging.getLogger(__name__)

class init(Command):
    base='svnadmin create svn_repo'

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
        'svn_repo/hooks/pre-revprop-change')
    # os.remove(revprop_hook)
    os.symlink('/bin/true', revprop_hook)
    # Use svnsync to clone svn=>svn
    sync('init', 'file://%s/svn_repo' % cmd.cwd(), remote).run_exc()
    sync('sync', 'file://%s/svn_repo' % cmd.cwd()).run_exc()
    # Use hgsubversion to clone svn=>hg
    hg.clone('file://%s/svn_repo' % cmd.cwd(), 'hg_repo').run_exc()

def setup_commit_hook(repo_dir, plugin_id):
    'Set up the svn post-commit hook'
    tpl_fn = pkg_resources.resource_filename(
        'forgescm', 'data/svn/post-commit_tmpl')
    tpl_text = open(tpl_fn).read()
    tt = genshi.template.NewTextTemplate(
        tpl_text, filepath=os.path.dirname(tpl_fn), filename=tpl_fn)
    context = dict(
        executable=sys.executable,
        repository=plugin_id,
        config=pylons.config['__file__'])
    strm = tt.generate(**context)
    fn = os.path.join(repo_dir, 'svn_repo/hooks/post-commit')
    with open(fn, 'w') as fp:
        fp.write(strm.render())
    os.chmod(fn, 0755)

    
