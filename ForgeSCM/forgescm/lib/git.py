import os
import sys
import shutil
import logging

import pkg_resources
import genshi
import pylons
from pymongo import bson
from dateutil.parser import parse as parse_dt

from pyforge.lib.helpers import find_executable
from forgescm import model as M
from .command import Command

log = logging.getLogger(__name__)

class init(Command):
    base='git init'

class clone(Command):
    base='git clone -n'

    # call this after a clone, since git clone always creates
    # a subdir, we need to move the git back to the already
    # existing mount-point directory
    # -- possibly could eliminate this if we use --bare
    def finish(self):
        path = self.cwd()
        tmp_git_path = os.path.join(path, self.args[-1])
        shutil.move(os.path.join(tmp_git_path, '.git'), os.path.join(path, '.git'))
        shutil.rmtree(os.path.join(path, tmp_git_path))

class scm_log(Command):
    base='git log'

def setup_scmweb(repo_name, repo_dir):
    return setup_gitweb(repo_name, repo_dir)

def setup_gitweb(repo_name, repo_dir):
    'Set up the GitWeb config file'
    tpl_fn = pkg_resources.resource_filename(
        'forgescm', 'data/gitweb.conf_tmpl')
    tpl_text = open(tpl_fn).read()
    tt = genshi.template.NewTextTemplate(
        tpl_text, filepath=os.path.dirname(tpl_fn), filename=tpl_fn)
    cfg_strm = tt.generate(
        my_uri='/_wsgi_/scm/' + repo_name,
        site_name='GitWeb Interface for ' + repo_name,
        project_root=repo_dir)
    cfg_fn = os.path.join(repo_dir, 'gitweb.conf')
    with open(cfg_fn, 'w') as fp:
        fp.write(cfg_strm.render())

def setup_commit_hook(repo_dir, plugin_id):
    'Set up the git post-commit hook'
    tpl_fn = pkg_resources.resource_filename(
        'forgescm', 'data/git/post-receive_tmpl')
    tpl_text = open(tpl_fn).read()
    tt = genshi.template.NewTextTemplate(
        tpl_text, filepath=os.path.dirname(tpl_fn), filename=tpl_fn)
    config = None
    if 'file' in pylons.config:
        config = pylons.config.__file__
    context = dict(
        executable=sys.executable,
        repository=plugin_id,
        config=config)
    strm = tt.generate(**context)
    fn = os.path.join(repo_dir, '.git/hooks/post-receive')
    with open(fn, 'w') as fp:
        fp.write(strm.render())
    os.chmod(fn, 0755)

class LogParser(object):

    def __init__(self, repo_id):
        self.repo_id = repo_id
        self.result = []

    def feed(self, line_iter):
        cur_line = line_iter.next()
        while True:
            try:
                if cur_line.startswith('commit'):
                    cur_line = self.parse_header(cur_line, line_iter)
                elif cur_line.startswith('diff --git'):
                    cur_line = self.parse_diff(cur_line, line_iter)
                elif cur_line.strip():
                    self.result[-1].summary += cur_line
                    # log.error('Unexpected line %r', cur_line)
                    cur_line = line_iter.next()
                else:
                    cur_line = line_iter.next()
            except StopIteration:
                break
        return self.result

    def parse_header(self, cur_line, line_iter):
        hash = cur_line.split()[-1].strip()
        log.debug('Parsing changeset %s', hash)
        r = M.Commit(
            repository_id=self.repo_id,
            hash=hash,
            summary='')
        while cur_line != '\n':
            cur_line = line_iter.next()
            if cur_line == '\n': break
            cmd, rest = cur_line.split(':', 1)
            result = self.parse_line(rest)
            if cur_line.startswith('Author:'):
                r.user = result
            elif cur_line.startswith('Date:'):
                r.date = parse_dt(result)
            elif cur_line != '\n':
                r.summary += cur_line
            elif cur_line == '\n':
                if r.summary: break
                else: cur_line = line_iter.next()
        if self.result and not self.result[-1].parents:
            self.result[-1].parents = [ r.hash ]
        self.result.append(r)
        if cur_line == '\n':
            cur_line = line_iter.next()
        return cur_line

    def parse_line(self, rest):
        return rest.lstrip()

    def parse_diff(self, cur_line, line_iter):
        cmdline = cur_line.split(' ')
        log.debug('Begin diff %s', cmdline)
        r = M.Patch(repository_id=self.result[-1].repository_id,
                    commit_id=self.result[-1]._id,
                    filename=cmdline[2][2:])
        text_lines = []
        while cur_line != '\n':
            cur_line = line_iter.next()
            if cur_line.startswith('diff'): break
            if cur_line != '\n': text_lines.append(cur_line)
        r.patch_text = bson.Binary(''.join(text_lines))
        if cur_line == '\n':
            cur_line = line_iter.next()
        return cur_line

