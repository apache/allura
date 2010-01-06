import os
import json
import shutil
import logging

import pylons
from pymongo import bson
from dateutil.parser import parse as parse_dt

from forgescm import model as M
from .command import Command

log = logging.getLogger(__name__)

class init(Command):
    base='hg init'

class clone(Command):
    base='hg clone'

class scm_log(Command):
    base='hg log'

def setup_commit_hook(repo_dir, plugin_id):
    text = '''[hooks]
incoming.notify_forge = python:forgescm.lib.hg.incoming_hook

[notify_forge]
repository = %s
config = %s
''' % (plugin_id, pylons.config.__file__)
    fn = os.path.join(repo_dir, '.hg/hgrc')
    with open(fn, 'a') as fp:
        fp.write(text)

def incoming_hook(ui, repo, node, **kwargs):
    ini_file = ui.config('notify_forge', 'config')
    repo_id = ui.config('notify_forge', 'repository')
    from pyforge.command import SendMessageCommand
    cmd = SendMessageCommand('sendmsg')
    msg = dict(hash=node)
    cmd.parse_args(['-c', repo_id, ini_file,
                    'react', 'scm.hg.refresh_commit',
                    json.dumps(msg)])
    cmd.command()

class LogParser(object):

    def __init__(self, repo_id):
        self.repo_id = repo_id
        self.result = []

    def feed(self, line_iter):
        try:
            cur_line = line_iter.next()
            while True:
                if cur_line.startswith('changeset:'):
                    cur_line = self.parse_header(cur_line, line_iter)
                elif cur_line.startswith('diff --git'):
                    cur_line = self.parse_diff(cur_line, line_iter)
                elif cur_line.strip():
                    log.error('Unexpected line %r', cur_line)
                    cur_line = line_iter.next()
                else:
                    cur_line = line_iter.next()
        except StopIteration:
            pass
        return self.result

    def parse_header(self, cur_line, line_iter):
        hdr, rev, hash = cur_line.split(':')
        rev = rev.strip()
        hash = hash.strip()
        log.info('Parsing changeset %s:%s', rev, hash)
        r = M.Commit(repository_id=self.repo_id,
                     rev=int(rev),
                     hash=hash)
        while cur_line != '\n':
            cur_line = line_iter.next()
            if cur_line == '\n': break
            cmd, rest = cur_line.split(':', 1)
            result = self.parse_line(rest)
            if cur_line.startswith('tag:'):
                r.tags.append(result)
            elif cur_line.startswith('parent:'):
                r.parents.append(result)
            elif cur_line.startswith('user:'):
                r.user = result
            elif cur_line.startswith('branch:'):
                r.branch = result
            elif cur_line.startswith('date:'):
                r.date = parse_dt(result)
            elif cur_line.startswith('summary:'):
                r.summary = result
            elif cur_line != '\n':
                assert False, 'Unknown header: %r' % cur_line
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

