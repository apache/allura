import os
import shutil
import string
import logging
import subprocess
from hashlib import sha1
from cStringIO import StringIO
from datetime import datetime

import tg
import pymongo
import pysvn
from pylons import c

from ming.base import Object
from ming.orm import MappedClass, FieldProperty, session
from ming.utils import LazyProperty

from allura import model as M
from allura.lib import helpers as h
from allura.model.repository import GitLikeTree

log = logging.getLogger(__name__)

class Repository(M.Repository):
    tool_name='SVN'
    repo_id='svn'
    type_s='SVN Repository'
    class __mongometa__:
        name='svn-repository'
    branches = FieldProperty([dict(name=str,object_id=str)])

    def __init__(self, **kw):
        super(Repository, self).__init__(**kw)
        self._impl = SVNImplementation(self)

    def readonly_clone_command(self):
        return 'svn checkout svn://%s' % self.scm_url_path

    def readwrite_clone_command(self):
        return 'svn checkout svn+ssh://%s@%s' % (c.user.username, self.scm_url_path)

    def _log(self, rev, skip, max_count):
        ci = self.commit(rev)
        if ci is None: return []
        return ci.log(int(skip), int(max_count))

    def compute_diffs(self): return

    def count(self, *args, **kwargs):
        return super(Repository, self).count(None)

    def log(self, branch=None, offset=0, limit=10):
        return list(self._log(rev=branch, skip=offset, max_count=limit))

    def latest(self, branch=None):
        if self._impl is None: return None
        if not self.heads: return None
        return self._impl.commit(self.heads[0].object_id)

class SVNImplementation(M.RepositoryImplementation):
    post_receive_template = string.Template(
        '#!/bin/bash\n'
        'curl -s $url\n')

    def __init__(self, repo):
        self._repo = repo

    @LazyProperty
    def _svn(self):
        return pysvn.Client()

    @LazyProperty
    def _url(self):
        return 'file://%s/%s' % (self._repo.fs_path, self._repo.name)

    def shorthand_for_commit(self, commit):
        return '[r%d]' % self._revno(commit.object_id)

    def url_for_commit(self, commit):
        return '%s%d/' % (
            self._repo.url(), self._revno(commit.object_id))

    def init(self):
        fullname = self._setup_paths()
        log.info('svn init %s', fullname)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        subprocess.call(['svnadmin', 'create', self._repo.name],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 cwd=self._repo.fs_path)
        self._setup_special_files()
        self._repo.status = 'ready'

    def refresh_heads(self):
        info = self._svn.info2(
            self._url,
            revision=pysvn.Revision(pysvn.opt_revision_kind.head),
            recurse=False)[0][1]
        oid = self._oid(info.rev.number)
        self._repo.heads = [ Object(name=None, object_id=oid) ]
        # Branches and tags aren't really supported in subversion
        self._repo.branches = []
        self._repo.repo_tags = []
        session(self._repo).flush()

    def commit(self, rev):
        if rev in ('HEAD', None):
            if not self._repo.heads: return None
            oid = self._repo.heads[0].object_id
        elif isinstance(rev, int) or rev.isdigit():
            oid = self._oid(rev)
        else:
            oid = rev
        result = M.Commit.query.get(object_id=oid)
        if result is None: return None
        result.set_context(self._repo)
        return result

    def new_commits(self, all_commits=False):
        head_revno = self._revno(self._repo.heads[0].object_id)
        oids = [ self._oid(revno) for revno in range(1, head_revno+1) ]
        if all_commits:
            return oids
        # Find max commit id -- everything greater than that will be "unknown"
        prefix = self._oid('')
        q = M.Commit.query.find(
            dict(
                type='commit',
                object_id={'$gt':prefix},
                ),
            dict(object_id=True)
            )
        seen_oids = set()
        for d in q.ming_cursor.cursor:
            oid = d['object_id']
            if not oid.startswith(prefix): break
            seen_oids.add(oid)
        return [
            oid for oid in oids if oid not in seen_oids ]

    def commit_context(self, commit):
        revno = int(commit.object_id.split(':')[1])
        prev,next=[],[]
        if revno > 1:
            prev = [ self.commit(revno - 1) ]
        if revno < self._revno(self._repo.heads[0].object_id):
            next = [ self.commit(revno + 1) ]
        return dict(prev=prev, next=next)

    def refresh_commit(self, ci, seen_object_ids):
        log.info('Refresh %r %r', ci, self._repo)
        revno = self._revno(ci.object_id)
        rev = pysvn.Revision(
            pysvn.opt_revision_kind.number,
            revno)
        log_entry = self._svn.log(
            self._url,
            revision_start=rev,
            limit=1,
            discover_changed_paths=True)[0]
        # Save commit metadata
        ci.committed = Object(
            name=log_entry.get('author', '--none--'),
            email='',
            date=datetime.fromtimestamp(log_entry.date))
        ci.authored=Object(ci.committed)
        ci.message=log_entry.message
        if revno > 1:
            parent_oid = self._oid(revno - 1)
            ci.parent_ids = [ parent_oid ]
        # Save diff info
        ci.diffs.added = []
        ci.diffs.removed = []
        ci.diffs.changed = []
        ci.diffs.copied = []
        lst = dict(
            A=ci.diffs.added,
            D=ci.diffs.removed,
            M=ci.diffs.changed,
            R=ci.diffs.changed)
        for path in log_entry.changed_paths:
            if path.copyfrom_path:
                ci.diffs.copied.append(dict(
                        old=h.really_unicode(path.copyfrom_path),
                        new=h.really_unicode(path.path)))
                continue
            lst[path.action].append(h.really_unicode(path.path))

    def compute_tree(self, commit, tree_path='/'):
        tree_path = tree_path[:-1]
        tree_id = self._tree_oid(commit.object_id, tree_path)
        tree, isnew = M.Tree.upsert(tree_id)
        if not isnew: return tree_id
        log.debug('Computing tree for %s: %s',
                 self._revno(commit.object_id), tree_path)
        revno = self._revno(commit.object_id)
        try:
            infos = self._svn.info2(
                self._url + tree_path,
                revision=pysvn.Revision(
                    pysvn.opt_revision_kind.number,
                    revno),
                depth=pysvn.depth.immediates)
        except pysvn.ClientError:
            tree.object_ids = []
            return tree_id
        gl_tree = GitLikeTree()
        log.debug('Compute tree for %d paths', len(infos))
        for path, info in infos[1:]:
            if info.kind == pysvn.node_kind.dir:
                oid = self._tree_oid(commit.object_id, path)
                gl_tree.set_blob(path, oid)
            elif info.kind == pysvn.node_kind.file:
                oid = self._blob_oid(commit.object_id, path)
                gl_tree.set_blob(path, oid)
                M.Blob.upsert(oid)
            else:
                assert False
        tree.object_ids = [
            Object(object_id=oid, name=name)
            for name, oid in gl_tree.blobs.iteritems() ]
        # Save last commit info
        log.debug('Save commit info for %d paths', len(infos))
        for i, (path, info) in enumerate(infos):
            if i==0:
                oid = tree_id
            else:
                oid = gl_tree.get_blob(path)
            lc, isnew = M.LastCommitFor.upsert(repo_id=self._repo._id, object_id=oid)
            if not isnew: continue
            lc.last_commit.author = lc.last_commit.author_email = info.last_changed_author
            lc.last_commit.date = datetime.fromtimestamp(info.last_changed_date)
            lc.last_commit.id = self._oid(info.last_changed_rev.number)
            lc.last_commit.href = '%s%d/' % (self._repo.url(), info.last_changed_rev.number)
            lc.last_commit.shortlink = '[r%d]' % info.last_changed_rev.number
            lc.last_commit.summary = ''
        session(tree).flush(tree)
        return tree_id

    def _tree_oid(self, commit_id, path):
        data = 'tree\n%s\n%s' % (commit_id, path)
        return sha1(data).hexdigest()

    def _blob_oid(self, commit_id, path):
        data = 'blob\n%s\n%s' % (commit_id, path)
        return sha1(data).hexdigest()

    def log(self, object_id, skip, count):
        revno = self._revno(object_id)
        result = []
        while count and revno:
            if skip == 0:
                result.append(self._oid(revno))
                count -= 1
            else:
                skip -= 1
            revno -= 1
        if revno:
            return result, [ self._oid(revno) ]
        else:
            return result, []

    def open_blob(self, blob):
        data = self._svn.cat(
            self._url + blob.path(),
            revision=pysvn.Revision(
                pysvn.opt_revision_kind.number,
                self._revno(blob.commit.object_id)))
        return StringIO(data)

    def _setup_receive_hook(self):
        'Set up the hg changegroup hook'
        text = self.post_receive_template.substitute(
            url=tg.config.get('base_url', 'http://localhost:8080')
            + '/auth/refresh_repo' + self._repo.url())
        fn = os.path.join(self._repo.fs_path, self._repo.name, 'hooks', 'post-commit')
        with open(fn, 'wb') as fp:
            fp.write(text)
        os.chmod(fn, 0755)

    def _tree_from_log(self, parent_ci, log_entry):
        '''Build a fake git-like tree from a parent commit and a log entry'''
        if parent_ci is None:
            root = GitLikeTree()
        else:
            session(parent_ci).flush() # need to make sure the tree is in mongo first
            try:
                parent_ci.tree
            except:
                self.refresh_commit(parent_ci, set())
            root = GitLikeTree.from_tree(parent_ci.tree)
        for path in log_entry.changed_paths:
            if path.action == 'D':
                root.del_blob(h.really_unicode(path.path))
            else:
                info = self._svn.info2(
                    self._url + h.really_unicode(path.path),
                    revision=log_entry.revision)[0]
                if info[1].kind == pysvn.node_kind.dir:
                    if path.get('copyfrom_path') and path.get('copyfrom_revision'):
                        # Directory copy
                        src_path = path['copyfrom_path']
                        src_ci = self._repo.commit(path['copyfrom_revision'].number)
                        src_tree = src_ci.tree.get_object(*src_path.split('/'))
                        root.set_tree(path.path, GitLikeTree.from_tree(src_tree))
                    else:
                        # Create empty directory
                        root.set_tree(path.path, GitLikeTree())
                else:
                    data = 'blob\n%s\n%s' % (
                        log_entry.revision.number,
                        path.path)
                    oid = sha1(data).hexdigest()
                    root.set_blob(h.really_unicode(path.path), oid)
        return root

    def _revno(self, oid):
        return int(oid.split(':')[1])

    def _oid(self, revno):
        return '%s:%s' % (self._repo._id, revno)

MappedClass.compile_all()
