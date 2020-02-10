#!/bin/env python

#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.


from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import
import os
import sys
import argparse
from datetime import datetime

import git
import pysvn
from mercurial import ui, hg, cmdutil
import six
from six.moves import range


def main(opts):
    if opts.type == 'git':
        repo = git.Repo(opts.repo_path, odbt=git.GitCmdObjectDB)
        cid = opts.cid
        path = opts.path.strip('/')
        tree = repo.commit(opts.cid).tree
        if path:
            tree = tree[path]
        names = [n.name for n in tree]
        impl = impl_git_tree if opts.full_tree else impl_git_node
    elif opts.type == 'hg':
        repo = hg.repository(HgUI(), six.ensure_str(opts.repo_path))
        cid = None if opts.cid == 'HEAD' else ['%s:0' % opts.cid]
        path = opts.path.strip('/')
        filenames = list(repo[
            'tip' if opts.cid == 'HEAD' else opts.cid].manifest().keys())
        filenames = [
            name for name in filenames if name.startswith(('%s/' % path).lstrip('/'))]
        names = set()
        for name in filenames:
            names.add(name.split('/')[0])
        names = list(names)
        impl = impl_hg_tree if opts.full_tree else impl_hg_node
    elif opts.type == 'svn':
        repo = pysvn.Client()
        if opts.cid == 'HEAD':
            cid = pysvn.Revision(pysvn.opt_revision_kind.head)
        else:
            cid = pysvn.Revision(pysvn.opt_revision_kind.number, opts.cid)
        path = opts.path.strip('/')
        names = []
        impl = impl_svn_tree if opts.full_tree else impl_svn_node

    sys.stdout.write('Timing %s' % ('full tree' if opts.full_tree else 'node'))
    sys.stdout.flush()
    total = 0.0
    for i in range(opts.count):
        sys.stdout.write('.')
        sys.stdout.flush()
        start = datetime.now()
        impl(repo, cid, path, names, opts.repo_path)
        end = datetime.now()
        total += (end - start).total_seconds()
    print()
    print('Total time:           %s' % total)
    print('Average time per run: %s' % (total / opts.count))


def impl_git_tree(repo, cid, path, names, *args):
    data = {}
    for name in names:
        #data[name] = repo.git.rev_list(cid, '--', os.path.join(path, name), max_count=1)
        data[name] = git.Commit.iter_items(
            repo, cid, os.path.join(path, name), max_count=1).next().hexsha
    return data


def impl_git_node(repo, cid, path, *args):
    # return repo.git.rev_list(cid, '--', path, max_count=1)
    return git.Commit.iter_items(repo, cid, path, max_count=1).next().hexsha


def impl_hg_tree(repo, cid, path, names, *args):
    m = cmdutil.match(repo, pats=[path], default=path)
    data = {}
    for name in names:
        rev_iter = cmdutil.walkchangerevs(
            repo, m, {'rev': cid}, lambda c, f: None)
        data[name] = rev_iter.next().hex()
    return data


def impl_hg_node(repo, cid, path, *args):
    m = cmdutil.match(repo, pats=[path], default=path)
    rev_iter = cmdutil.walkchangerevs(repo, m, {'rev': cid}, lambda c, f: None)
    return rev_iter.next().hex()


def impl_svn_tree(repo, cid, path, names, repo_path, *args):
    infos = repo.info2(
        'file://%s/%s' % (repo_path, path),
        revision=cid,
        depth=pysvn.depth.immediates)
    data = {}
    for name, info in infos[1:]:
        data[name] = info.last_changed_rev
    return data


def impl_svn_node(repo, cid, path, names, repo_path, *args):
    logs = repo.log(
        'file://%s/%s' % (repo_path, path),
        revision_start=cid,
        limit=1)
    return logs[0].revision.number


class HgUI(ui.ui):

    '''Hg UI subclass that suppresses reporting of untrusted hgrc files.'''

    def __init__(self, *args, **kwargs):
        super(HgUI, self).__init__(*args, **kwargs)
        self._reportuntrusted = False


def parse_opts():
    parser = argparse.ArgumentParser(
        description='Benchmark getting LCD from repo tool')
    parser.add_argument('--type', default='git', dest='type',
                        help='Type of repository being tested.')
    parser.add_argument('--repo-path', dest='repo_path', required=True,
                        help='Path to the repository to test against')
    parser.add_argument('--commit', default='HEAD', dest='cid',
                        help='Commit ID or revision number to test against')
    parser.add_argument('--path', default='', dest='path',
                        help='Path within the repository to test against')
    parser.add_argument('--count', type=int, default=100, dest='count',
                        help='Number of times to execute')
    parser.add_argument(
        '--full-tree', action='store_true', default=False, dest='full_tree',
        help='Time full tree listing instead of just the single node')
    return parser.parse_args()

if __name__ == '__main__':
    main(parse_opts())
