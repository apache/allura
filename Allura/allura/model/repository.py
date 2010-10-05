import os
import stat
import errno
import string
import mimetypes
import logging
from datetime import datetime
from collections import defaultdict

import pylons
from tg import config
import pymongo.bson

from ming import schema as S
from ming.utils import LazyProperty
from ming.orm import MappedClass, FieldProperty, session

from allura.lib.patience import SequenceMatcher
from allura.lib import helpers as h

from .artifact import Artifact
from .auth import User
from .session import repository_orm_session

log = logging.getLogger(__name__)

class Repository(Artifact):
    repo_id='repo'
    type_s='Repository'
    class __mongometa__:
        name='generic-repository'

    name=FieldProperty(str)
    tool=FieldProperty(str)
    fs_path=FieldProperty(str)
    url_path=FieldProperty(str)
    status=FieldProperty(str)
    email_address=''
    additional_viewable_extensions=FieldProperty(str)
    heads = FieldProperty([dict(name=str,object_id=str)])
    repo_tags = FieldProperty([dict(name=str,object_id=str)])

    def __init__(self, **kw):
        if 'name' in kw and 'tool' in kw:
            if 'fs_path' not in kw:
                kw['fs_path'] = '/' + os.path.join(
                    kw['tool'],
                    pylons.c.project.url()[1:])
            if 'url_path' not in kw:
                kw['url_path'] = pylons.c.project.url()
        super(Repository, self).__init__(**kw)

    def __repr__(self):
        return '<%s %s>' % (
            self.__class__.__name__,
            self.full_fs_path)

    def commit(self, revision):
        raise NotImplementedError, 'commit'

    def new_commits(self):
        '''Return any commit object_ids in the native repo that are not (yet) stored
        in the database in reverse-topological order'''
        raise NotImplementedError, 'commit'

    def _log(self, rev, skip, max_count):
        ci = self.commit(rev)
        if ci is None: return []
        return ci.log(int(skip), int(max_count))

    def log(self, branch='master', offset=0, limit=10):
        return list(self._log(rev=branch, skip=offset, max_count=limit))

    def count(self, branch='master'):
        try:
            ci = self.commit(branch)
            if ci is None: return 0
            return ci.count_revisions()
        except:
            log.exception('Error getting repo count')
            return 0

    def latest(self, branch='master'):
        if self._impl is None: return None
        try:
            return self.commit(branch)
        except:
            return None

    def url(self):
        return self.app_config.url()

    def shorthand_id(self):
        return self.name

    def index(self):
        result = Artifact.index(self)
        result.update(
            name_s=self.name,
            type_s=self.type_s)
        return result

    @property
    def full_fs_path(self):
        return os.path.join(self.fs_path, self.name)

    def scm_host(self):
        return self.tool + config.get('scm.host', '.' + pylons.request.host)

    @property
    def scm_url_path(self):
        return self.scm_host() + self.url_path + self.name

    def init(self):
        raise NotImplementedError, 'init'

    @LazyProperty
    def _additional_viewable_extensions(self):
        ext_list = self.additional_viewable_extensions or ''
        ext_list = [ext.strip() for ext in ext_list.split(',') if ext]
        ext_list += [ '.ini', '.gitignore', '.svnignore' ]
        return ext_list

    def guess_type(self, name):
        '''Guess the mime type and encoding of a given filename'''
        content_type, encoding = mimetypes.guess_type(name)
        if not content_type.startswith('text/'):
            fn, ext = os.path.splitext(name)
            if ext in self._additional_viewable_extensions:
                content_type, encoding = 'text/plain', None
            if content_type is None:
                content_type, encoding = 'application/octet-stream', None
        return content_type, encoding

    def refresh(self, CommitClass):
        '''Find any new commits in the repository and update'''
        BATCH_SIZE=100
        sess = session(CommitClass)
        log.info('Refreshing repository %s', self)
        commit_ids = self.new_commits()
        log.info('... %d new commits', len(commit_ids))
        # Refresh history
        i=0
        for i, oid in enumerate(commit_ids):
            ci, isnew = CommitClass.upsert(self.repo_id, oid)
            if self._id not in ci.repositories:
                # update the commit's repo list
                ci.query.update(
                    dict(_id=ci._id),
                    {'$push':dict(repositories=self._id)})
            if not isnew:
                 # race condition, let the other proc handle it
                sess.expunge(ci)
                continue
            ci.respositories = [ self._id ]
            ci.set_context(self)
            ci.refresh()
            if (i+1) % BATCH_SIZE == 0:
                log.info('...... flushing %d commits (%d total)',
                         BATCH_SIZE, (i+1))
                sess.flush()
                sess.clear()
        log.info('...... flushing %d commits (%d total)',
                 BATCH_SIZE, i)
        sess.flush()
        sess.clear()
        # Compute diffs on new commits
        log.info('... computing diffs')
        for i, oid in enumerate(commit_ids):
            ci = self.commit(oid)
            ci.compute_diffs()
            if (i+1) % BATCH_SIZE == 0:
                log.info('...... flushing %d commits (%d total)',
                         BATCH_SIZE, (i+1))
                sess.flush()
                sess.clear()
        log.info('...... flushing %d commits (%d total)',
                 BATCH_SIZE, i)
        sess.flush()
        sess.clear()
        log.info('... refreshed repository %s.  Found %d new commits',
                 self, len(commit_ids))
        return len(commit_ids)

    def _setup_paths(self, create_repo_dir=True):
        if not self.fs_path.endswith('/'): self.fs_path += '/'
        fullname = os.path.join(self.fs_path, self.name)
        try:
            os.makedirs(fullname if create_repo_dir else self.fs_path)
        except OSError, e: # pragma no cover
            if e.errno != errno.EEXIST: raise
        return fullname

    def _setup_special_files(self):
        magic_file = os.path.join(self.fs_path, self.name, '.SOURCEFORGE-REPOSITORY')
        with open(magic_file, 'w') as f:
            f.write(self.repo_id)
        os.chmod(magic_file, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
        self._setup_receive_hook(
            pylons.c.app.config.script_name())

    def _setup_receive_hook(self):
        raise NotImplementedError, '_setup_post_receive_hook'

class RepoObject(MappedClass):
    class __mongometa__:
        session = repository_orm_session
        name='repo_object'
        indexes = [ 'repo_id', 'object_id' ]
        unique_indexes = [ ('repo_id', 'object_id') ]

    # ID Fields
    _id = FieldProperty(S.ObjectId)
    repo_id = FieldProperty(str) # either 'hg', 'git', or the repo path (for svn)
    object_id = FieldProperty(str)
    last_commit = FieldProperty(dict(
        date=datetime,
        author=str,
        id=str,
        href=str))

    @classmethod
    def upsert(cls, repo_id, object_id):
        isnew = False
        r = cls.query.get(repo_id=repo_id, object_id=object_id)
        if r is not None:
            return r, isnew
        try:
            r = cls(repo_id=repo_id, object_id=object_id)
            session(r).flush(r)
            isnew = True
        except pymongo.errors.DuplicateKeyError:
            session(r).expunge(r)
            r = cls.query.get(repo_id=repo_id, object_id=object_id)
        return r, isnew

    def set_last_commit(self, ci):
        '''Update the last_commit field based on the passed in commit'''
        self.last_commit.author = ci.authored.name
        self.last_commit.date = ci.authored.date
        self.last_commit.id = ci.object_id
        self.last_commit.href = ci.url()

    def __repr__(self):
        return '<%s %s>' % (
            self.__class__.__name__, self.object_id)

    def index_id(self):
        return repr(self)

    def set_context(self, context):
        '''Set ephemeral (unsaved) attributes based on a context object'''
        raise NotImplementedError, 'set_context'

    def refresh(self):
        '''Refresh the repo object from a 'native' object'''
        raise NotImplementedError, 'refresh'

class LogCache(RepoObject):
    '''Class to store nothing but lists of commit IDs in topo sort order'''
    class __mongometa__:
        name='log_cache'
    type_s = 'LogCache'

    object_ids = FieldProperty([str])
    candidates = FieldProperty([str])

    @classmethod
    def get(cls, repo, object_id):
        lc, new = cls.upsert(repo.repo_id, object_id)
        if not lc.object_ids:
            ci = repo.commit(object_id)
            lc.object_ids, lc.candidates = ci._log(0, 50)
        return lc

class Commit(RepoObject):
    class __mongometa__:
        name='repo_commit'
        indexes = RepoObject.__mongometa__.indexes + [ 'parent_ids' ]
    type_s = 'Commit'

    # File data
    tree_id = FieldProperty(str)
    diffs = FieldProperty(dict(
            added=[dict(old=str, new=str)],
            removed=[dict(old=str, new=str)],
            changed=[dict(old=str, new=str)]))
    # Commit metadata
    committed = FieldProperty(
        dict(name=str,
             email=str,
             date=datetime))
    authored = FieldProperty(
        dict(name=str,
             email=str,
             date=datetime))
    message = FieldProperty(str)
    parent_ids = FieldProperty([str])
    extra = FieldProperty([dict(name=str, value=str)])
     # All repos that potentially reference this commit
    repositories=FieldProperty([S.ObjectId])

    def __init__(self, **kw):
        super(Commit, self).__init__(**kw)
        # Ephemeral attrs
        self.repo = None

    def set_context(self, repo):
        self.repo = repo

    def context(self):
        '''Returns {'prev':Commit, 'next':Commit}'''
        raise NotImplementedError, 'context'

    @LazyProperty
    def author_url(self):
        u = User.by_email_address(self.authored.email)
        if u: return u.url()

    @LazyProperty
    def committer_url(self):
        u = User.by_email_address(self.committed.email)
        if u: return u.url()

    def primary(self):
        return self

    def shorthand_id(self):
        return '[%s]' % self.object_id[:6]

    def url(self):
        return self.repo.url() + 'ci/' + self.object_id + '/'

    def dump_ref(self):
        return CommitReference(
            commit_class=self.__class__,
            repo_id=self.repo_id,
            object_id=self.object_id)

    def log(self, skip, count):
        oids = list(self.log_iter(skip, count))
        commits = self.query.find(dict(
                repo_id=self.repo_id,
                object_id={'$in':oids}))
        commits_by_oid = {}
        for ci in commits:
            ci.set_context(self.repo)
            commits_by_oid[ci.object_id] = ci
        return [ commits_by_oid[oid] for oid in oids ]

    def log_iter(self, skip, count):
        seen_oids = set()
        candidates = [ self.object_id ]
        while candidates and count:
            candidate = candidates.pop()
            if candidate in seen_oids: continue
            lc = LogCache.get(self.repo, candidate)
            oids = lc.object_ids
            candidates += lc.candidates
            for oid in oids:
                if oid in seen_oids: continue
                seen_oids.add(oid)
                if count == 0:
                    break
                elif skip == 0:
                    yield oid
                    count -= 1
                else:
                    skip -= 1

    def count_revisions(self):
        seen_oids = set()
        candidates = [ self.object_id ]
        while candidates:
            candidate = candidates.pop()
            if candidate in seen_oids: continue
            lc = LogCache.get(self.repo, candidate)
            for oid in lc.object_ids:
                seen_oids.add(oid)
            candidates += lc.candidates
        return len(seen_oids)

    def _log(self, skip, count):
        '''Return a list of object_ids beginning at this commit and continuing
        in topological sort order.  Also return a list of 'next commit' options'''
        raise NotImplementedError, '_log'

class Tree(RepoObject):
    README_NAMES=set(['readme.txt','README.txt','README.TXT','README'])
    class __mongometa__:
        name='repo_tree'
    type_s = 'Tree'

    trees = FieldProperty({str:str}) # trees[oid] = name
    blobs = FieldProperty({str:str}) # blobs[oid] = name

    def __init__(self, **kw):
        super(Tree, self).__init__(**kw)
        # Ephemeral attrs
        self.repo = None
        self.commit = None
        self.parent = None
        self.name = None

    @classmethod
    def diff(cls, a, b):
        '''Recursive diff of two tree objects, yielding DiffObjects'''
        if a is None:
            yield DiffObject(None, b)
        elif b is None:
            yield DiffObject(a, None)
        else:
            # Yield blob differences
            a_blob_ids = set(a.blobs)
            b_blob_ids = set(b.blobs)
            for a_oid in a_blob_ids - b_blob_ids:
                a_obj = a._get_blob(a.blobs[a_oid], a_oid)
                b_obj = b.get_blob(a_obj.name)
                if b_obj: b_blob_ids.remove(b_obj.object_id)
                yield DiffObject(a_obj, b_obj)
            for b_oid in b_blob_ids - a_blob_ids:
                b_obj = a._get_blob(b.blobs[b_oid], b_oid)
                a_obj = a.get_blob(b_obj.name)
                yield DiffObject(a_obj, b_obj)
            # Yield tree differences (this is the recursive step)
            a_tree_ids = set(a.trees)
            b_tree_ids = set(b.trees)
            for a_oid in a_tree_ids - b_tree_ids:
                a_obj = a._get_tree(a.trees[a_oid], a_oid)
                b_obj = b.get_tree(a_obj.name)
                if b_obj: b_tree_ids.remove(b_obj.object_id)
                for x in cls.diff(a_obj, b_obj): yield x
            for b_oid in b_tree_ids - a_tree_ids:
                b_obj = b._get_tree(b.trees[b_oid], b_oid)
                a_obj = a.get_tree(b_obj.name)
                for x in cls.diff(a_obj, b_obj): yield x

    def set_context(self, commit_or_tree, name=None):
        assert commit_or_tree is not self
        self.repo = commit_or_tree.repo
        if isinstance(commit_or_tree, Tree):
            self.parent = commit_or_tree
            self.commit = commit_or_tree.commit
        else:
            self.commit = commit_or_tree
        self.name = name

    def readme(self):
        for oid, name in self.blobs.iteritems():
            if name in self.README_NAMES:
                blob = self._get_blob(name, oid)
                return h.really_unicode(blob.text)
        return ''

    def ls(self):
        for oid, name in sorted(self.trees.iteritems(), key=lambda (o,n):n):
            ci = self._get_tree(name, oid).last_commit
            yield dict(kind='DIR',
                       last_commit=ci,
                       name=name,
                       href=name)
        for oid, name in sorted(self.blobs.iteritems(), key=lambda (o,n):n):
            ci = self._get_blob(name, oid).last_commit
            yield dict(kind='FILE',
                       last_commit=ci,
                       name=name,
                       href=name)

    def render(self, indent=''):
        for o in self.blobs:
            yield indent + o.name
        for o in self.trees:
            t = self._get_tree(o.name, o.object_id)
            yield indent + o.name
            for line in t.render(indent=indent+'    '):
                yield line

    def index_id(self):
        return repr(self)

    def path(self):
        if self.parent:
            assert self.parent is not self
            return self.parent.path() + self.name + '/'
        else:
            return '/'

    def url(self):
        return self.commit.url() + 'tree' + self.path()

    @classmethod
    def from_repo_object(cls, repo, obj):
        raise NotImplementedError, 'from_repo_object'

    def _get_tree(self, name, oid):
        raise NotImplementedError, '_get_tree'

    def _get_blob(self, name, oid):
        raise NotImplementedError, '_get_blob'

    def is_blob(self, name):
        for oid, bname in self.blobs.iteritems():
            if bname == name: return True
        return False

    def get_tree(self, name):
        for oid, oname in self.trees.iteritems():
            if oname == name:
                return self._get_tree(name, oid)
        else:
            return None

    def get_blob(self, name, path_parts=None):
        if path_parts:
            t = self.get_tree(path_parts[0])
            if t:
                return t.get_blob(name, path_parts[1:])
            else:
                return None
        for oid, oname in self.blobs.iteritems():
            if oname == name:
                return self._get_blob(name, oid)
        else:
            return None

class Blob(RepoObject):
    class __mongometa__:
        session = repository_orm_session
        name='repo_blob'
    type_s = 'Blob'

    def __init__(self, **kw):
        super(Blob, self).__init__(**kw)
        # Ephemeral attrs
        self.repo = None
        self.commit = None
        self.tree = None
        self.name = None

    def set_context(self, tree, name):
        self.repo = tree.repo
        self.commit = tree.commit
        self.tree = tree
        self.name = name

    @LazyProperty
    def _content_type_encoding(self):
        return self.repo.guess_type(self.name)

    @LazyProperty
    def content_type(self):
        return self._content_type_encoding[0]

    @LazyProperty
    def content_encoding(self):
        return self._content_type_encoding[1]

    @LazyProperty
    def prev_commit(self):
        if self.commit.object_id != self.last_commit.id:
            return self.repo.commit(self.last_commit.id)
        elif self.commit.parent_ids:
            prev_ci = self.repo.commit(self.commit.parent_ids[0])
            path_parts = self.path().split('/')[1:-1]
            prev_blob = prev_ci.tree.get_blob(self.name, path_parts)
            return self.repo.commit(prev_blob.last_commit.id)
        else:
            return None

    def url(self):
        return self.tree.url() + h.really_unicode(self.name)

    def path(self):
        return self.tree.path() + h.really_unicode(self.name)

    @property
    def has_html_view(self):
        return self.content_type.startswith('text/')

    @property
    def has_image_view(self):
        return self.content_type.startswith('image/')

    def context(self):
        '''Returns {'prev':Blob, 'next':Blob}'''
        raise NotImplementedError, 'context'

    @classmethod
    def from_repo_object(cls, repo, obj):
        raise NotImplementedError, 'from_repo_object'

    def __iter__(self):
        return iter([])

    @classmethod
    def diff(cls, v0, v1):
        differ = SequenceMatcher(v0, v1)
        return differ.get_opcodes()

class CommitReference(object):
    def __init__(self, commit_class, repo_id, commit_id):
        self.commit_class = commit_class
        self.repo_id = repo_id
        self.commit_id = commit_id

    @property
    def artifact(self):
        return self.commit_class.query.get(
            repo_id=self.repo_id, commit_id=self.commit_id)

class DiffObject(object):
    a_path = b_path = None
    a_object_id = b_object_id = None
    is_new = False
    is_deleted = False

    def __init__(self, a, b):
        if a:
            self.a_path = a.path()
            self.a_object_id = a.object_id
        else:
            self.is_new = True
        if b:
            self.b_path = b.path()
            self.b_object_id = b.object_id
        else:
            self.is_deleted = True

MappedClass.compile_all()
