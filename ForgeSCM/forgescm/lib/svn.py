import os
import logging

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

class scm_log(Command):
    base='git svn log'

    def cwd(self):
        return Command.cwd(self) + '/git'

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
