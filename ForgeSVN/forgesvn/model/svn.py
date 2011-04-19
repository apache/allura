import os
import shutil
import string
import logging
import subprocess
from hashlib import sha1
from cStringIO import StringIO
from datetime import datetime

import tg
import pysvn

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

    def get_last_commit(self, obj):
        lc, isnew = M.LastCommitFor.upsert(repo_id=self._id, object_id=obj.object_id)
        if not isnew and lc.last_commit.id:
            return lc.last_commit
        try:
            info = self._impl._svn.info2(
                self._impl._url + obj.path(),
                revision=self._impl._revision(obj.commit.object_id),
                depth=pysvn.depth.empty)[0][1]
            lc.last_commit.author = lc.last_commit.author_email = info.last_changed_author
            lc.last_commit.date = datetime.utcfromtimestamp(info.last_changed_date)
            lc.last_commit.id = self._impl._oid(info.last_changed_rev.number)
            lc.last_commit.href = '%s%d/' % (self.url(), info.last_changed_rev.number)
            lc.last_commit.shortlink = '[r%d]' % info.last_changed_rev.number
            lc.last_commit.summary = ''
            return lc.last_commit
        except:
            log.exception('Cannot get last commit for %s', obj)
            return dict(
                author=None,
                author_email=None,
                author_url=None,
                date=None,
                id=None,
                href=None,
                shortlink=None,
                summary=None)

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
        return 'file://%s%s' % (self._repo.fs_path, self._repo.name)

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

    def clone_from(self, source_url):
        '''Initialize a repo as a clone of another using svnsync'''
        self.init()
        log.info('Initialize %r as a clone of %s',
                 self._repo, source_url)
        p = subprocess.call(['svnsync', 'init', self._url, source_url],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
        assert p == 0
        p = subprocess.call(['svnsync', '--non-interactive', 'sync', self._url],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
        assert p == 0
        self._repo.status = 'analyzing'
        session(self._repo).flush()
        log.info('... %r cloned, analyzing', self._repo)
        self._repo.refresh()
        self._repo.status = 'ready'
        log.info('... %s ready', self._repo)
        session(self._repo).flush()

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
        rev = self._revision(ci.object_id)
        try:
            log_entry = self._svn.log(
                self._url,
                revision_start=rev,
                limit=1,
                discover_changed_paths=True)[0]
        except pysvn.ClientError:
            log.info('ClientError processing %r %r, treating as empty', ci, self._repo, exc_info=True)
            log_entry = Object(date='', message='', changed_paths=[])
        # Save commit metadata
        ci.committed = Object(
            name=log_entry.get('author', '--none--'),
            email='',
            date=datetime.utcfromtimestamp(log_entry.date))
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
        rev = self._revision(commit.object_id)
        try:
            infos = self._svn.info2(
                self._url + tree_path,
                revision=rev,
                depth=pysvn.depth.immediates)
        except pysvn.ClientError:
            log.exception('Error computing tree for %s: %s(%s)',
                          self._repo, commit, tree_path)
            tree.delete()
            return None
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
        session(tree).flush(tree)
        return tree_id

    def _tree_oid(self, commit_id, path):
        data = 'tree\n%s\n%s' % (commit_id, h.really_unicode(path))
        return sha1(data.encode('utf-8')).hexdigest()

    def _blob_oid(self, commit_id, path):
        data = 'blob\n%s\n%s' % (commit_id, h.really_unicode(path))
        return sha1(data.encode('utf-8')).hexdigest()

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
            revision=self._revision(blob.commit.object_id))
        return StringIO(data)

    def _setup_hooks(self):
        'Set up the post-commit and pre-revprop-change hooks'
        text = self.post_receive_template.substitute(
            url=tg.config.get('base_url', 'http://localhost:8080')
            + '/auth/refresh_repo' + self._repo.url())
        fn = os.path.join(self._repo.fs_path, self._repo.name, 'hooks', 'post-commit')
        with open(fn, 'wb') as fp:
            fp.write(text)
        os.chmod(fn, 0755)
        fn = os.path.join(self._repo.fs_path, self._repo.name, 'hooks', 'pre-revprop-change')
        with open(fn, 'wb') as fp:
            fp.write('#!/bin/sh\n')
        os.chmod(fn, 0755)

    def _revno(self, oid):
        return int(oid.split(':')[1])

    def _revision(self, oid):
        return pysvn.Revision(
            pysvn.opt_revision_kind.number,
            self._revno(oid))

    def _oid(self, revno):
        return '%s:%s' % (self._repo._id, revno)

MappedClass.compile_all()
