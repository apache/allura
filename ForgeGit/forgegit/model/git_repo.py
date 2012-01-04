import os
import shutil
import string
import logging
import random
from collections import namedtuple
from datetime import datetime

import tg
import git
from pymongo.errors import DuplicateKeyError

from ming.base import Object
from ming.orm import Mapper, session, mapper
from ming.utils import LazyProperty

from allura.lib import helpers as h
from allura.lib import utils
from allura.model.repository import topological_sort
from allura import model as M

log = logging.getLogger(__name__)

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
        '# The following line is required for site integration, do not remove/modify\n'
        'curl -s $url\n')

    def __init__(self, repo):
        self._repo = repo

    @LazyProperty
    def _git(self):
        try:
            return git.Repo(self._repo.full_fs_path)
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

    def clone_from(self, source_url):
        '''Initialize a repo as a clone of another'''
        fullname = self._setup_paths(create_repo_dir=False)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        log.info('Initialize %r as a clone of %s',
                 self._repo, source_url)
        repo = git.Repo.clone_from(
            source_url,
            to_path=fullname,
            bare=True)
        self.__dict__['_git'] = repo
        self._setup_special_files()
        self._repo.status = 'analyzing'
        session(self._repo).flush()
        log.info('... %r cloned, analyzing', self._repo)
        self._repo.refresh(notify=False)
        self._repo.status = 'ready'
        log.info('... %s ready', self._repo)
        session(self._repo).flush()

    def commit(self, rev):
        '''Return a Commit object.  rev can be object_id or a branch/tag name'''
        result = M.Commit.query.get(object_id=rev)
        if result is None:
            # find the id by branch/tag name
            try:
                impl = self._git.rev_parse(str(rev) + '^0')
                result = M.Commit.query.get(object_id=impl.hexsha)
            except Exception:
                url = ''
                try:
                    from tg import request
                    url = ' at ' + request.url
                except:
                    pass
                log.exception('Error with rev_parse(%s)%s' % (str(rev) + '^0', url))
        if result is None: return None
        result.set_context(self._repo)
        return result

    def all_commit_ids(self):
        seen = set()
        for head in self._git.heads:
            for ci in self._git.iter_commits(head, topo_order=True):
                if ci.binsha in seen: continue
                seen.add(ci.binsha)
                yield ci.hexsha

    def new_commits(self, all_commits=False):
        graph = {}

        to_visit = [ self._git.commit(rev=hd.object_id) for hd in self._repo.heads ]
        while to_visit:
            obj = to_visit.pop()
            if obj.hexsha in graph: continue
            if not all_commits:
                # Look up the object
                if M.Commit.query.find(dict(object_id=obj.hexsha)).count():
                    graph[obj.hexsha] = set() # mark as parentless
                    continue
            graph[obj.hexsha] = set(p.hexsha for p in obj.parents)
            to_visit += obj.parents
        return list(topological_sort(graph))

    def commit_context(self, commit):
        prev_ids = commit.parent_ids
        prev = M.Commit.query.find(dict(
                object_id={'$in':prev_ids})).all()
        next = M.Commit.query.find(dict(
                parent_ids=commit.object_id,
                repositories=self._repo._id)).all()
        for ci in prev + next:
            ci.set_context(self._repo)
        return dict(prev=prev, next=next)

    def refresh_heads(self):
        self._repo.heads = [
            Object(name=head.name, object_id=head.commit.hexsha)
            for head in self._git.heads
            if head.is_valid() ]
        self._repo.branches = [
            Object(name=head.name, object_id=head.commit.hexsha)
            for head in self._git.branches
            if head.is_valid() ]
        self._repo.repo_tags = [
            Object(name=tag.name, object_id=tag.commit.hexsha)
            for tag in self._git.tags
            if tag.is_valid() ]
        session(self._repo).flush()

    def refresh_commit(self, ci, seen_object_ids):
        obj = self._git.commit(ci.object_id)
        ci.tree_id = obj.tree.hexsha
        # Save commit metadata
        ci.committed = Object(
            name=h.really_unicode(obj.committer.name),
            email=h.really_unicode(obj.committer.email),
            date=datetime.utcfromtimestamp(obj.committed_date))
        ci.authored=Object(
            name=h.really_unicode(obj.author.name),
            email=h.really_unicode(obj.author.email),
            date=datetime.utcfromtimestamp(obj.authored_date))
        ci.message=h.really_unicode(obj.message or '')
        ci.parent_ids=[ p.hexsha for p in obj.parents ]
        # Save commit tree
        tree, isnew = M.Tree.upsert(obj.tree.hexsha)
        seen_object_ids.add(obj.tree.binsha)
        if isnew:
            tree.set_context(ci)
            self._refresh_tree(tree, obj.tree, seen_object_ids)

    def refresh_commit_info(self, oid, seen):
        from allura.model.repo import CommitDoc
        if CommitDoc.m.find(dict(_id=oid)).count():
            return False
        try:
            ci = self._git.rev_parse(oid)
            ci_doc = CommitDoc(dict(
                    _id=ci.hexsha,
                    tree_id=ci.tree.hexsha,
                    committed = Object(
                        name=h.really_unicode(ci.committer.name),
                        email=h.really_unicode(ci.committer.email),
                        date=datetime.utcfromtimestamp(
                            ci.committed_date-ci.committer_tz_offset)),
                    authored = Object(
                        name=h.really_unicode(ci.author.name),
                        email=h.really_unicode(ci.author.email),
                        date=datetime.utcfromtimestamp(
                            ci.authored_date-ci.author_tz_offset)),
                    message=h.really_unicode(ci.message or ''),
                    child_ids=[],
                    parent_ids = [ p.hexsha for p in ci.parents ]))
            ci_doc.m.insert(safe=True)
        except DuplicateKeyError:
            return False
        self.refresh_tree_info(ci.tree, seen)
        return True

    def refresh_tree_info(self, tree, seen):
        from allura.model.repo import TreeDoc
        if tree.binsha in seen: return
        seen.add(tree.binsha)
        doc = TreeDoc(dict(
                _id=tree.hexsha,
                tree_ids=[],
                blob_ids=[],
                other_ids=[]))
        for o in tree:
            obj = Object(
                name=h.really_unicode(o.name),
                id=o.hexsha)
            if o.type == 'tree':
                self.refresh_tree_info(o, seen)
                doc.tree_ids.append(obj)
            elif o.type == 'blob':
                doc.blob_ids.append(obj)
            else:
                obj.type = o.type
                doc.other_ids.append(obj)
        doc.m.save(safe=False)

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
            self._object(blob.object_id).data_stream)

    def _setup_hooks(self):
        'Set up the git post-commit hook'
        text = self.post_receive_template.substitute(
            url=tg.config.get('base_url', 'http://localhost:8080')
            + '/auth/refresh_repo' + self._repo.url())
        fn = os.path.join(self._repo.fs_path, self._repo.name, 'hooks', 'post-receive')
        with open(fn, 'w') as fp:
            fp.write(text)
        os.chmod(fn, 0755)

    def _refresh_tree(self, tree, obj, seen_object_ids):
        tree.object_ids = [
            Object(object_id=o.hexsha, name=h.really_unicode(o.name))
            for o in obj
            if o.type in ('blob', 'tree') ] # submodules poorly supported by GitPython
        for o in obj.trees:
            if o.binsha in seen_object_ids: continue
            subtree, isnew = M.Tree.upsert(o.hexsha)
            seen_object_ids.add(o.binsha)
            if isnew:
                subtree.set_context(tree, o.name)
                self._refresh_tree(subtree, o, seen_object_ids)
        for o in obj.blobs:
            if o.binsha in seen_object_ids: continue
            blob, isnew = M.Blob.upsert(o.hexsha)
            seen_object_ids.add(o.binsha)
        for o in obj.trees:
            if o.binsha in seen_object_ids: continue
            subtree, isnew = M.Tree.upsert(o.hexsha)
            seen_object_ids.add(o.binsha)
            if isnew:
                subtree.set_context(tree, o.name)
                self._refresh_tree(subtree, o, seen_object_ids)
        for o in obj.blobs:
            if o.binsha in seen_object_ids: continue
            blob, isnew = M.Blob.upsert(o.hexsha)
            seen_object_ids.add(o.binsha)

    def _object(self, oid):
        evens = oid[::2]
        odds = oid[1::2]
        binsha = ''
        for e,o in zip(evens, odds):
            binsha += chr(int(e+o, 16))
        return git.Object.new_from_sha(self._git, binsha)

    def symbolics_for_commit(self, commit):
        branch_heads, tags = super(self.__class__, self).symbolics_for_commit(commit)
        containing_branches = self._git.git.branch(contains=commit.object_id)
        containing_branches = [br.strip(' *') for br in containing_branches.split('\n')]
        return containing_branches, tags

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
