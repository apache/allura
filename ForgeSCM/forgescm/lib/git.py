import os
import shutil
import logging

import pkg_resources
import genshi
from pymongo import bson

from forgescm import model as M
from .command import Command

log = logging.getLogger(__name__)

class init(Command):
    base='git init'

class clone(Command):
    base='git clone'

class scm_log(Command):
    base='git log -p'

def setup_gitweb(repo_name, repo_dir):
    # Set up the GitWeb config file
    tpl_fn = pkg_resources.resource_filename('forgescm', 'data/gitweb.conf_tmpl')
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
        r = M.Commit.make(dict(repository_id=self.repo_id,
                               hash=hash,
                               summary=''))
        while cur_line != '\n':
            cur_line = line_iter.next()
            if cur_line == '\n': break
            cmd, rest = cur_line.split(':', 1)
            result = self.parse_line(rest)
            if cur_line.startswith('Author:'):
                r.user = result
            elif cur_line.startswith('Date:'):
                r.date = result
            elif cur_line != '\n':
                r.summary += cur_line
            elif cur_line == '\n':
                if r.summary: break
                else: cur_line = line_iter.next()
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
        log.debug('Begin diff %s', cmdline)
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

