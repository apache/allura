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
        result = []
        for revno in range(1, head_revno+1):
            oid = self._oid(revno)
            if all_commits or M.Commit.query.find(dict(object_id=oid)).count() == 0:
                result.append(oid)
        return result

    def commit_context(self, commit):
        revno = int(commit.object_id.split(':')[1])
        prev,next=[],[]
        if revno > 1:
            prev = [ self.commit(revno - 1) ]
        if revno < self._revno(self._repo.heads[0].object_id):
            next = [ self.commit(revno + 1) ]
        return dict(prev=prev, next=next)

    def refresh_commit(self, ci, seen_object_ids):
        log.info('Refresh %r', ci)
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
            name=log_entry.author,
            email='',
            date=datetime.fromtimestamp(log_entry.date))
        ci.authored=Object(ci.committed)
        ci.message=log_entry.message
        if revno > 1:
            parent_oid = self._oid(revno - 1)
            parent_ci = self.commit(parent_oid)
            ci.parent_ids = [ parent_oid ]
        else:
            parent_ci = None
        # Save commit tree (must build a fake git-like tree from the log entry)
        fake_tree = self._tree_from_log(parent_ci, log_entry)
        ci.tree_id = fake_tree.hex()
        tree, isnew = M.Tree.upsert(fake_tree.hex())
        if isnew:
            tree.set_context(ci)
            self._refresh_tree(tree, fake_tree)

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
            url=tg.config.get('base_url', 'localhost:8080')
            + self._repo.url()[1:] + 'refresh')
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
                try:
                    data = self._svn.cat(
                        self._url + h.really_unicode(path.path),
                        revision=log_entry.revision)
                    oid = sha1('blob\n' + data).hexdigest()
                    root.set_blob(h.really_unicode(path.path), oid)
                except pysvn.ClientError:
                    # probably a directory; create an empty file named '.'
                    data = ''
                    oid = sha1(data).hexdigest()
                    root.set_blob(h.really_unicode(path.path) + '/.', oid)
        return root

    def _refresh_tree(self, tree, obj):
        tree.object_ids=Object(
            (o.hex(), name)
            for name, o in obj.trees.iteritems())
        tree.object_ids.update(
            (oid, name)
            for name, oid in obj.blobs.iteritems())
        for name, o in obj.trees.iteritems():
            subtree, isnew = M.Tree.upsert(o.hex())
            if isnew:
                subtree.set_context(tree, name)
                self._refresh_tree(subtree, o)
        for name, oid in obj.blobs.iteritems():
            blob, isnew = M.Blob.upsert(oid)

    def _revno(self, oid):
        return int(oid.split(':')[1])

    def _oid(self, revno):
        return '%s:%s' % (self._repo._id, revno)

MappedClass.compile_all()
