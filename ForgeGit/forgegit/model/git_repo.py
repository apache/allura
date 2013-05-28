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

import os
import sys
import shutil
import string
import logging
import random
import itertools
from collections import namedtuple
from datetime import datetime
from glob import glob
import gzip

import tg
import git
import gitdb
from pylons import app_globals as g
from pylons import tmpl_context as c
from pymongo.errors import DuplicateKeyError
from paste.deploy.converters import asbool

from ming.base import Object
from ming.orm import Mapper, session, mapper
from ming.utils import LazyProperty

from allura.lib import helpers as h
from allura.lib import utils
from allura.model.repository import topological_sort
from allura import model as M

log = logging.getLogger(__name__)

gitdb.util.mman = gitdb.util.mman.__class__(
    max_open_handles=128)

class Repository(M.Repository):
    tool_name='Git'
    repo_id='git'
    type_s='Git Repository'
    class __mongometa__:
        name='git-repository'

    @LazyProperty
    def _impl(self):
        return GitImplementation(self)

    def suggested_clone_dest_path(self):
        return super(Repository, self).suggested_clone_dest_path()[:-4]

    def clone_url(self, category, username=''):
        return super(Repository, self).clone_url(category, username)[:-4]

    def merge_command(self, merge_request):
        '''Return the command to merge a given commit to a given target branch'''
        return 'git checkout %s\ngit fetch %s\ngit merge %s' % (
            merge_request.target_branch,
            merge_request.downstream_repo_url,
            merge_request.downstream.commit_id,
        )

class GitImplementation(M.RepositoryImplementation):
    post_receive_template = string.Template(
        '#!/bin/bash\n'
        '# The following is required for site integration, do not remove/modify.\n'
        '# Place user hook code in post-receive-user and it will be called from here.\n'
        'curl -s $url\n'
        '\n'
        'DIR="$$(dirname "$${BASH_SOURCE[0]}")"\n'
        'if [ -x $$DIR/post-receive-user ]; then\n'
        '  exec $$DIR/post-receive-user\n'
        'fi')

    def __init__(self, repo):
        self._repo = repo

    @LazyProperty
    def _git(self):
        try:
            return git.Repo(self._repo.full_fs_path, odbt=git.GitCmdObjectDB)
        except (git.exc.NoSuchPathError, git.exc.InvalidGitRepositoryError), err:
            log.error('Problem looking up repo: %r', err)
            return None

    def init(self):
        fullname = self._setup_paths()
        log.info('git init %s', fullname)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        repo = git.Repo.init(
            path=fullname,
            mkdir=True,
            quiet=True,
            bare=True,
            shared='all')
        self.__dict__['_git'] = repo
        self._setup_special_files()
        self._repo.status = 'ready'

    def can_hotcopy(self, source_url):
        enabled = asbool(tg.config.get('scm.git.hotcopy', True))
        is_local = os.path.exists(source_url)
        requested = self._repo.app.config.options.get('hotcopy', False)
        return enabled and is_local and requested

    def clone_from(self, source_url):
        '''Initialize a repo as a clone of another'''
        self._repo.status = 'cloning'
        session(self._repo).flush(self._repo)
        log.info('Initialize %r as a clone of %s',
                 self._repo, source_url)
        try:
            fullname = self._setup_paths(create_repo_dir=False)
            if os.path.exists(fullname):
                shutil.rmtree(fullname)
            if self.can_hotcopy(source_url):
                shutil.copytree(source_url, fullname)
                post_receive = os.path.join(self._repo.full_fs_path, 'hooks', 'post-receive')
                if os.path.exists(post_receive):
                    os.rename(post_receive, post_receive + '-user')
                repo = git.Repo(fullname)
            else:
                repo = git.Repo.clone_from(
                    source_url,
                    to_path=fullname,
                    bare=True)
            self.__dict__['_git'] = repo
            self._setup_special_files(source_url)
        except:
            self._repo.status = 'ready'
            session(self._repo).flush(self._repo)
            raise

    def commit(self, rev):
        '''Return a Commit object.  rev can be _id or a branch/tag name'''
        cache = getattr(c, 'model_cache', '') or M.repo.ModelCache()
        result = cache.get(M.repo.Commit, dict(_id=rev))
        if result is None:
            # find the id by branch/tag name
            try:
                impl = self._git.rev_parse(str(rev) + '^0')
                result = cache.get(M.repo.Commit, dict(_id=impl.hexsha))
            except Exception:
                url = ''
                try:
                    from tg import request
                    url = ' at ' + request.url
                except:
                    pass
                log.exception('Error with rev_parse(%s)%s' % (str(rev) + '^0', url))
        if result:
            result.set_context(self._repo)
        return result

    def all_commit_ids(self):
        """Yield commit ids, starting with the head(s) of the commit tree and
        ending with the root (first commit).
        """
        if not self._git.head.is_valid():
            return  # empty repo
        seen = set()
        for ci in self._git.iter_commits(all=True, topo_order=True):
            if ci.binsha in seen: continue
            seen.add(ci.binsha)
            yield ci.hexsha

    def new_commits(self, all_commits=False):
        graph = {}

        to_visit = [ self._git.commit(rev=hd.object_id) for hd in self.heads ]
        while to_visit:
            obj = to_visit.pop()
            if obj.hexsha in graph: continue
            if not all_commits:
                # Look up the object
                if M.repo.Commit.query.find(dict(_id=obj.hexsha)).count():
                    graph[obj.hexsha] = set() # mark as parentless
                    continue
            graph[obj.hexsha] = set(p.hexsha for p in obj.parents)
            to_visit += obj.parents
        return list(topological_sort(graph))

    def refresh_commit_info(self, oid, seen, lazy=True):
        from allura.model.repo import CommitDoc
        ci_doc = CommitDoc.m.get(_id=oid)
        if ci_doc and lazy: return False
        ci = self._git.rev_parse(oid)
        args = dict(
            tree_id=ci.tree.hexsha,
            committed = Object(
                name=h.really_unicode(ci.committer.name),
                email=h.really_unicode(ci.committer.email),
                date=datetime.utcfromtimestamp(ci.committed_date)),
            authored = Object(
                name=h.really_unicode(ci.author.name),
                email=h.really_unicode(ci.author.email),
                date=datetime.utcfromtimestamp(ci.authored_date)),
            message=h.really_unicode(ci.message or ''),
            child_ids=[],
            parent_ids = [ p.hexsha for p in ci.parents ])
        if ci_doc:
            ci_doc.update(**args)
            ci_doc.m.save()
        else:
            ci_doc = CommitDoc(dict(args, _id=ci.hexsha))
            try:
                ci_doc.m.insert(safe=True)
            except DuplicateKeyError:
                if lazy: return False
        self.refresh_tree_info(ci.tree, seen, lazy)
        return True

    def refresh_tree_info(self, tree, seen, lazy=True):
        from allura.model.repo import TreeDoc
        if lazy and tree.binsha in seen: return
        seen.add(tree.binsha)
        doc = TreeDoc(dict(
                _id=tree.hexsha,
                tree_ids=[],
                blob_ids=[],
                other_ids=[]))
        for o in tree:
            if o.type == 'submodule':
                continue
            obj = Object(
                name=h.really_unicode(o.name),
                id=o.hexsha)
            if o.type == 'tree':
                self.refresh_tree_info(o, seen, lazy)
                doc.tree_ids.append(obj)
            elif o.type == 'blob':
                doc.blob_ids.append(obj)
            else:
                obj.type = o.type
                doc.other_ids.append(obj)
        doc.m.save(safe=False)
        return doc

    def commits(self, path=None, rev=None, skip=None, limit=None):
        params = dict(paths=path)
        if rev is not None:
            params['rev'] = rev
        if skip is not None:
            params['skip'] = skip
        if limit is not None:
            params['max_count'] = limit
        return (c.hexsha for c in self._git.iter_commits(**params))

    def commits_count(self, path=None, rev=None):
        commit = self._git.commit(rev)
        return commit.count(path)

    def log(self, object_id, skip, count):
        obj = self._git.commit(object_id)
        candidates = [ obj ]
        result = []
        seen = set()
        while count and candidates:
            candidates.sort(key=lambda c:c.committed_date)
            obj = candidates.pop(-1)
            if obj.hexsha in seen: continue
            seen.add(obj.hexsha)
            if skip == 0:
                result.append(obj.hexsha)
                count -= 1
            else:
                skip -= 1
            candidates += obj.parents
        return result, [ p.hexsha for p in candidates ]

    def open_blob(self, blob):
        return _OpenedGitBlob(
            self._object(blob._id).data_stream)

    def blob_size(self, blob):
        return self._object(blob._id).data_stream.size

    def _setup_hooks(self, source_path=None):
        'Set up the git post-commit hook'
        text = self.post_receive_template.substitute(
            url=tg.config.get('base_url', 'http://localhost:8080')
            + '/auth/refresh_repo' + self._repo.url())
        fn = os.path.join(self._repo.fs_path, self._repo.name, 'hooks', 'post-receive')
        with open(fn, 'w') as fp:
            fp.write(text)
        os.chmod(fn, 0755)

    def _object(self, oid):
        evens = oid[::2]
        odds = oid[1::2]
        binsha = ''
        for e,o in zip(evens, odds):
            binsha += chr(int(e+o, 16))
        return git.Object.new_from_sha(self._git, binsha)

    def symbolics_for_commit(self, commit):
        try:
            branches = [b.name for b in self.branches if b.object_id == commit._id]
            tags = [t.name for t in self.tags if t.object_id == commit._id]
            return branches, tags
        except git.GitCommandError:
            return [], []

    def compute_tree_new(self, commit, tree_path='/'):
        ci = self._git.rev_parse(commit._id)
        tree = self.refresh_tree_info(ci.tree, set())
        return tree._id

    def tarball(self, commit, path=None):
        if not os.path.exists(self._repo.tarball_path):
            os.makedirs(self._repo.tarball_path)
        archive_name = self._repo.tarball_filename(commit)
        filename = os.path.join(self._repo.tarball_path, '%s%s' % (archive_name, '.zip'))
        tmpfilename = os.path.join(self._repo.tarball_path, '%s%s' % (archive_name, '.tmp'))
        try:
            with open(tmpfilename, 'wb') as archive_file:
                self._git.archive(archive_file, format='zip', treeish=commit, prefix=archive_name + '/')
            os.rename(tmpfilename, filename)
        finally:
            if os.path.exists(tmpfilename):
                os.remove(tmpfilename)

    def is_empty(self):
        return not self._git or len(self._git.heads) == 0

    @LazyProperty
    def heads(self):
        return [Object(name=b.name, object_id=b.commit.hexsha) for b in self._git.heads if b.is_valid()]

    @LazyProperty
    def branches(self):
        return [Object(name=b.name, object_id=b.commit.hexsha) for b in self._git.branches if b.is_valid()]

    @LazyProperty
    def tags(self):
        return [Object(name=t.name, object_id=t.commit.hexsha) for t in self._git.tags if t.is_valid()]


class _OpenedGitBlob(object):
    CHUNK_SIZE=4096

    def __init__(self, stream):
        self._stream = stream

    def read(self):
        return self._stream.read()

    def __iter__(self):
        '''
        Yields one line at a time, reading from the stream
        '''
        buffer = ''
        while True:
            # Replenish buffer until we have a line break
            while '\n' not in buffer:
                chars = self._stream.read(self.CHUNK_SIZE)
                if not chars: break
                buffer += chars
            if not buffer: break
            eol = buffer.find('\n')
            if eol == -1:
                # end without \n
                yield buffer
                break
            yield buffer[:eol+1]
            buffer = buffer[eol+1:]

    def close(self):
        pass

Mapper.compile_all()
