import os
import shutil
import logging

from pymongo import bson

from forgescm import model as M
from .command import Command

log = logging.getLogger(__name__)

class init(Command):
    base='hg init'

class clone(Command):
    base='hg clone'

class scm_log(Command):
    base='hg log -g -p'

class LogParser(object):

    def __init__(self, repo_id):
        self.repo_id = repo_id
        self.result = []

    def feed(self, line_iter):
        cur_line = line_iter.next()
        while True:
            try:
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
                break
        return self.result

    def parse_header(self, cur_line, line_iter):
        hash = cur_line.split(':')[2].strip()
        log.debug('Parsing changeset %s', hash)
        r = M.Commit.make(dict(repository_id=self.repo_id,
                               hash=hash))
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
                r.date = result
            elif cur_line.startswith('summary:'):
                r.summary = result
            elif cur_line != '\n':
                assert False, 'Unknown header: %r' % cur_line
        r.m.save()
        if self.result and not self.result[-1].parents:
            self.result[-1].parents = [ r.hash ]
            self.result[-1].m.save()
        self.result.append(r)
        if cur_line == '\n':
            cur_line = line_iter.next()
        return cur_line

    def parse_line(self, rest):
        return rest.lstrip()

    def parse_diff(self, cur_line, line_iter):
        cmdline = cur_line.split(' ')
        r = M.Patch.make(dict(repository_id=self.result[-1].repository_id,
                              commit_id=self.result[-1]._id,
                              filename=cmdline[2][2:]))
        text_lines = []
        while cur_line != '\n':
            cur_line = line_iter.next()
            if cur_line.startswith('diff'): break
            if cur_line != '\n': text_lines.append(cur_line)
        r.patch_text = bson.Binary(''.join(text_lines))
        r.m.save()
        if cur_line == '\n':
            cur_line = line_iter.next()
        return cur_line

