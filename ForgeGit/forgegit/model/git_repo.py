import os
import shutil
import string
import logging
from datetime import datetime
from cStringIO import StringIO
from heapq import heappush, heappop

import tg
import git

from ming.base import Object
from ming.orm import MappedClass, FieldProperty, session
from ming.utils import LazyProperty

from allura import model as M

log = logging.getLogger(__name__)

class GitRepository(M.Repository):
    repo_id='git'
    type_s='Git Repository'
    post_receive_template = string.Template('''#!/bin/bash
curl $url > /dev/null 2>&1
''')
    class __mongometa__:
        name='git-repository'
    branches = FieldProperty([dict(name=str,object_id=str)])

    def init(self):
        '''Initialize a bare and empty repo'''
        fullname = self._setup_paths()
        log.info('git init %s', fullname)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        self.__dict__['_impl'] = git.Repo.init(
            path=fullname,
            mkdir=True,
            quiet=True,
            bare=True,
            shared='all')
        self._setup_special_files()
        self.status = 'ready'

    def clone_from(self, source_path):
        '''Initialize a repo as a clone of another'''
        fullname = self._setup_paths(create_repo_dir=False)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        self.__dict__['_impl'] = git.Repo.clone_from(
            source_path,
            to_path=fullname,
            bare=True)
        requests = os.path.join(fullname, 'refs', 'requests')
        shutil.rmtree(requests, ignore_errors=True)
        self._setup_special_files()
        self.status = 'analyzing'
        session(self).flush()
        self.refresh()
        self.status = 'ready'
        session(self).flush()

    def new_commits(self):
        result = []
        seen_commits = set()
        for head in self.heads:
            for ci_impl in self._impl.iter_commits(rev=head.object_id):
                if GitCommit.query.get(repo_id='git', object_id=ci_impl.hexsha):
                    break
                else:
                    result.append(ci_impl.hexsha)
                    seen_commits.add(ci_impl.hexsha)
        result.reverse()
        return result

    def refresh(self):
        self.heads = [
            Object(name=head.name, object_id=head.commit.hexsha)
            for head in self._impl.heads
            if head.is_valid() ]
        self.branches = [
            Object(name=head.name, object_id=head.commit.hexsha)
            for head in self._impl.branches
            if head.is_valid() ]
        self.repo_tags = [
            Object(name=tag.name, object_id=tag.commit.hexsha)
            for tag in self._impl.tags
            if tag.is_valid() ]
        session(self).flush()
        return super(GitRepository, self).refresh(GitCommit)

    def commit(self, rev):
        result = GitCommit.query.get(repo_id='git', object_id=rev)
        if result is None:
            impl = self._impl.rev_parse(str(rev) + '^0')
            result = GitCommit.query.get(repo_id='git', object_id=impl.hexsha)
        if result is None: return None
        result.set_context(self)
        return result

    @LazyProperty
    def _impl(self):
        try:
            return git.Repo(self.full_fs_path)
        except (git.exc.NoSuchPathError, git.exc.InvalidGitRepositoryError), err:
            log.error('Problem looking up repo: %r', err)
            return None

    def _setup_receive_hook(self, plugin_id):
        'Set up the git post-commit hook'
        text = self.post_receive_template.substitute(
            url=tg.config.get('base_url', 'localhost:8080') + self.url()[1:] + 'refresh')
        fn = os.path.join(self.fs_path, self.name, 'hooks', 'post-receive')
        with open(fn, 'w') as fp:
            fp.write(text)
        os.chmod(fn, 0755)

class GitCommit(M.Commit):
    type_s='GitCommit'

    def _log(self, skip, count):
        candidates = [ (self.committed.date, self) ]
        result = []
        seen = set()
        while count and candidates:
            ci = heappop(candidates)[1]
            if ci.object_id in seen: continue
            seen.add(ci.object_id)
            if skip == 0:
                result.append(ci.object_id)
                count -= 1
            else:
                skip -= 1
            for parent_id in ci.parent_ids:
                p_ci = self.repo.commit(parent_id)
                heappush(candidates, (p_ci.committed.date or datetime.min, p_ci))
        return result, [ ci.object_id for (dt,ci) in candidates ]

    def refresh(self):
        obj = self._impl
        self.tree_id = obj.tree.hexsha
        # Save commit metadata
        self.committed = Object(
            name=obj.committer.name,
            email=obj.committer.email,
            date=datetime.fromtimestamp(
                obj.committed_date-obj.committer_tz_offset))
        self.authored=Object(
            name=obj.author.name,
            email=obj.author.email,
            date=datetime.fromtimestamp(
                obj.authored_date-obj.author_tz_offset))
        self.message=obj.message or ''
        self.parent_ids=[ p.hexsha for p in obj.parents ]
        # Save commit tree
        tree, isnew = GitTree.upsert('git', obj.tree.hexsha)
        if isnew:
            tree.set_context(self)
            tree.set_last_commit(self)
            tree.refresh()
        else:
            session(tree).expunge(tree)

    def compute_diffs(self):
        self.diffs.added = []
        self.diffs.removed = []
        self.diffs.changed = []
        if self.parent_ids:
            parent = self.repo.commit(self.parent_ids[0])
            for diff in GitTree.diff(parent.tree, self.tree):
                d = Object(old=diff.a_path, new=diff.b_path)
                if diff.is_new:
                    self.diffs.added.append(d)
                elif diff.is_deleted:
                    self.diffs.removed.append(d)
                else:
                    self.diffs.changed.append(d)

    @LazyProperty
    def _impl(self):
        return self.repo._impl.commit(self.object_id)

    def get_path(self, path):
        if path.startswith('/'): path = path[1:]
        path_parts = path.split('/')
        return self.tree.get_blob(path_parts[-1], path_parts[:-1])

    def diff(self, other=None, paths=None, create_patch=False):
        if other is None: other = self.parent_ids[0]
        my_impl = self._impl
        other_impl = self.repo.commit(other)._impl
        result = my_impl.diff(
            other=other_impl,
            paths=paths,
            create_patch=create_patch)
        return result

    def diff_summarize(self):
        if self.parent_ids:
            for d in self.diff():
                if d.deleted_file:
                    yield 'remove', d.a_blob.path
                elif d.new_file:
                    yield 'add', d.b_blob.path
                else:
                    yield 'change', d.a_blob.path
        else:
            for x in self.tree().ls():
                yield 'add', x['href']

    def context(self):
        prev_ids = self.parent_ids
        prev = GitCommit.query.find(dict(
                repo_id='git',
                object_id={'$in':prev_ids})).all()
        next = GitCommit.query.find(dict(
                repo_id='git',
                parent_ids=self.object_id,
                repositories=self.repo._id)).all()
        for ci in prev + next:
            ci.repo = self.repo
        return dict(prev=prev, next=next)

    @LazyProperty
    def tree(self):
        t = GitTree.query.get(repo_id='git', object_id=self.tree_id)
        t.set_context(self)
        return t

class GitTree(M.Tree):
    repo_id='git'

    def refresh(self):
        obj = self._impl
        self.trees=Object(
            (o.hexsha, o.name)
            for o in obj.trees)
        self.blobs=Object(
            (o.hexsha, o.name)
            for o in obj.blobs)
        for o in obj.trees:
            tree, isnew = GitTree.upsert('git', o.hexsha)
            if isnew:
                tree.set_context(self, o.name)
                tree.set_last_commit(self.commit)
                tree.refresh()
        for o in obj.blobs:
            blob, isnew = GitBlob.upsert('git', o.hexsha)
            if isnew:
                blob.set_context(self, o.name)
                blob.set_last_commit(self.commit)

    @LazyProperty
    def _impl(self):
        if self.parent:
            return self.parent._impl[self.name]
        else:
            return self.commit._impl.tree

    def shorthand_id(self):
        return '[%s]' % (self.object_id[:6])

    def _get_tree(self, name, oid):
        t = GitTree.query.get(repo_id='git', object_id=oid)
        t.set_context(self, name)
        return t

    def _get_blob(self, name, oid):
        b = GitBlob.query.get(repo_id='git', object_id=oid)
        b.set_context(self, name)
        return b

class GitBlob(M.Blob):

    @property
    def _impl(self):
        return self.tree._impl[self.name]

    def __iter__(self):
        fp = StringIO(self.text)
        return iter(fp)

    @LazyProperty
    def text(self):
        return self._impl.data_stream.read()

    @LazyProperty
    def next_commit(self):
        try:
            path = self.path()
            cur = self.commit
            next = cur.context()['next']
            while next:
                cur = next[0]
                next = cur.context()['next']
                other_blob = cur.get_path(path)
                if other_blob is None or other_blob.object_id != self.object_id:
                    return cur
        except:
            log.exception('Lookup prev_commit')
            return None

    def context(self):
        path = self.path()[1:]
        prev = self.prev_commit
        next = self.next_commit
        if prev is not None: prev = prev.get_path(path)
        if next is not None: next = next.get_path(path)
        return dict(
            prev=prev,
            next=next)

MappedClass.compile_all()
