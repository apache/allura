import os
import stat
import errno
import string
import mimetypes
import logging
from hashlib import sha1
from datetime import datetime
from collections import defaultdict

import pylons
from tg import config
import pymongo.bson

from ming import schema as S
from ming.base import Object
from ming.utils import LazyProperty
from ming.orm import MappedClass, FieldProperty, session

from allura.lib.patience import SequenceMatcher
from allura.lib import helpers as h

from .artifact import Artifact
from .auth import User
from .session import repository_orm_session, project_orm_session

log = logging.getLogger(__name__)

class RepositoryImplementation(object):

    # Repository-specific code
    def init(self):
        raise NotImplementedError, 'init'

    def clone_from(self, source_path):
        raise NotImplementedError, 'clone_from'

    def commit(self, revision):
        raise NotImplementedError, 'commit'

    def new_commits(self, all_commits=False):
        '''Return any commit object_ids in the native repo that are not (yet) stored
        in the database in topological order (parents first)'''
        raise NotImplementedError, 'commit'

    def commit_context(self, object_id):
        '''Returns {'prev':Commit, 'next':Commit}'''
        raise NotImplementedError, 'context'

    def refresh_heads(self):
        '''Sets repository metadata such as heads, tags, and branches'''
        raise NotImplementedError, 'refresh_heads'

    def refresh_commit(self, ci, seen_object_ids):
        '''Refresh the data in the commit object 'ci' with data from the repo'''
        raise NotImplementedError, 'refresh_heads'

    def _setup_receive_hook(self):
        '''Install a hook in the repository that will ping the refresh url for
        the repo'''
        raise NotImplementedError, '_setup_receive_hook'

    def log(self, object_id, skip, count):
        '''Return a list of object_ids beginning at the given commit ID and continuing
        to the parent nodes in a breadth-first traversal.  Also return a list of 'next commit' options
        (these are candidates for he next commit after 'count' commits have been
        exhausted).'''
        raise NotImplementedError, '_log'

    def open_blob(self, blob):
        '''Return a file-like object that contains the contents of the blob'''
        raise NotImplementedError, 'open_blob'

    def shorthand_for_commit(self, commit):
        return '[%s]' % commit.object_id[:6]

    def url_for_commit(self, commit):
        return '%sci/%s/' % (self._repo.url(), commit.object_id)

    def _setup_paths(self, create_repo_dir=True):
        if not self._repo.fs_path.endswith('/'): self._repo.fs_path += '/'
        fullname = os.path.join(self._repo.fs_path, self._repo.name)
        try:
            os.makedirs(fullname if create_repo_dir else self._repo.fs_path)
        except OSError, e: # pragma no cover
            if e.errno != errno.EEXIST: raise
        return fullname

    def _setup_special_files(self):
        magic_file = os.path.join(self._repo.fs_path, self._repo.name, '.SOURCEFORGE-REPOSITORY')
        with open(magic_file, 'w') as f:
            f.write(self._repo.repo_id)
        os.chmod(magic_file, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
        self._setup_receive_hook()

class Repository(Artifact):
    BATCH_SIZE=100
    class __mongometa__:
        name='generic-repository'
    _impl = None
    repo_id='repo'
    type_s='Repository'

    name=FieldProperty(str)
    tool=FieldProperty(str)
    fs_path=FieldProperty(str)
    url_path=FieldProperty(str)
    status=FieldProperty(str)
    email_address=''
    additional_viewable_extensions=FieldProperty(str)
    heads = FieldProperty([dict(name=str,object_id=str, count=int)])
    branches = FieldProperty([dict(name=str,object_id=str, count=int)])
    repo_tags = FieldProperty([dict(name=str,object_id=str, count=int)])
    upstream_repo = FieldProperty(dict(name=str,url=str))

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

    # Proxy to _impl
    def init(self):
        return self._impl.init()
    def commit(self, rev):
        return self._impl.commit(rev)
    def commit_context(self, commit):
        return self._impl.commit_context(commit)
    def open_blob(self, blob):
        return self._impl.open_blob(blob)
    def shorthand_for_commit(self, commit):
        return self._impl.shorthand_for_commit(commit)
    def url_for_commit(self, commit):
        return self._impl.url_for_commit(commit)

    def _log(self, rev, skip, max_count):
        ci = self.commit(rev)
        if ci is None: return []
        return ci.log(int(skip), int(max_count))

    def init_as_clone(self, source_path, source_name, source_url):
        self.upstream_repo.name = source_name
        self.upstream_repo.url = source_url
        session(self).flush(self)
        self._impl.clone_from(source_path)

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

    @LazyProperty
    def _additional_viewable_extensions(self):
        ext_list = self.additional_viewable_extensions or ''
        ext_list = [ext.strip() for ext in ext_list.split(',') if ext]
        ext_list += [ '.ini', '.gitignore', '.svnignore', 'README' ]
        return ext_list

    def guess_type(self, name):
        '''Guess the mime type and encoding of a given filename'''
        content_type, encoding = mimetypes.guess_type(name)
        if content_type is None or not content_type.startswith('text/'):
            fn, ext = os.path.splitext(name)
            ext = ext or fn
            if ext in self._additional_viewable_extensions:
                content_type, encoding = 'text/plain', None
            if content_type is None:
                content_type, encoding = 'application/octet-stream', None
        return content_type, encoding

    def refresh(self, all_commits=False):
        '''Find any new commits in the repository and update'''
        self._impl.refresh_heads()
        self.status = 'analyzing'
        session(self).flush()
        sess = session(Commit)
        log.info('Refreshing repository %s', self)
        commit_ids = self._impl.new_commits(all_commits)
        log.info('... %d new commits', len(commit_ids))
        # Refresh history
        i=0
        seen_object_ids = set()
        for i, oid in enumerate(commit_ids):
            if len(seen_object_ids) > 10000:
                log.info('... flushing seen object cache')
                seen_object_ids = set()
            ci, isnew = Commit.upsert(oid)
            if self._id not in ci.repositories:
                # update the commit's repo list
                ci.query.update(
                    dict(_id=ci._id),
                    {'$push':dict(repositories=self._id)})
            if not isnew and not all_commits:
                 # race condition, let the other proc handle it
                sess.expunge(ci)
                continue
            ci.respositories = [ self._id ]
            ci.set_context(self)
            self._impl.refresh_commit(ci, seen_object_ids)
            if (i+1) % self.BATCH_SIZE == 0:
                log.info('...... flushing %d commits (%d total)',
                         self.BATCH_SIZE, (i+1))
                sess.flush()
                sess.clear()
        log.info('...... flushing %d commits (%d total)',
                 i % self.BATCH_SIZE, i)
        sess.flush()
        sess.clear()
        self.compute_diffs(commit_ids)
        for head in self.heads + self.branches + self.tags:
            ci = self.commit(head.object_id)
            if ci is not None:
                head.count = ci.count_revisions()
        session(self).flush()
        return len(commit_ids)

    def compute_diffs(self, commit_ids=None):
        if commit_ids is None:
            commit_ids = self._impl.new_commits(all_commits=True)
        sess = session(Commit)
        # Compute diffs on new commits
        log.info('... computing diffs')
        seen_objects = {}
        i=0
        for i, oid in enumerate(commit_ids):
            ci = self._impl.commit(oid)
            ci.compute_diffs(seen_objects)
            if (i+1) % self.BATCH_SIZE == 0:
                seen_objects = {}
                log.info('...... flushing %d commits (%d total)',
                         self.BATCH_SIZE, (i+1))
                sess.flush()
                sess.clear()
        log.info('...... flushing %d commits (%d total)',
                 i % self.BATCH_SIZE, i)
        sess.flush()
        sess.clear()
        log.info('... refreshed repository %s.  Found %d new commits',
                 self, len(commit_ids))
        self.status = 'ready'

class LastCommitFor(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name='last_commit_for'
        unique_indexes = [ ('repo_id', 'object_id') ]

    _id = FieldProperty(S.ObjectId)
    repo_id = FieldProperty(S.ObjectId)
    object_id = FieldProperty(str)
    last_commit = FieldProperty(dict(
        date=datetime,
        author=str,
        author_email=str,
        author_url=str,
        id=str,
        href=str,
        shortlink=str,
        summary=str))

    @classmethod
    def upsert(cls, repo_id, object_id):
        isnew = False
        r = cls.query.get(repo_id=repo_id, object_id=object_id)
        if r is not None: return r, isnew
        try:
            r = cls(repo_id=repo_id, object_id=object_id)
            session(r).flush(r)
            isnew = True
        except pymongo.errors.DuplicateKeyError:
            session(r).expunge(r)
            r = cls.query.get(repo_id=repo_id, object_id=object_id)
        return r, isnew

class RepoObject(MappedClass):
    class __mongometa__:
        session = repository_orm_session
        name='repo_object'
        polymorphic_on = 'type'
        polymorphic_identity=None
        indexes = [ 'parent_ids' ]
        unique_indexes = [ 'object_id' ]

    # ID Fields
    _id = FieldProperty(S.ObjectId)
    type = FieldProperty(str)
    repo_id = FieldProperty(S.Deprecated)
    object_id = FieldProperty(str)
    last_commit=FieldProperty(S.Deprecated)

    @classmethod
    def upsert(cls, object_id):
        isnew = False
        r = cls.query.get(object_id=object_id)
        if r is not None:
            return r, isnew
        try:
            r = cls(
                type=cls.__mongometa__.polymorphic_identity,
                object_id=object_id)
            session(r).flush(r)
            isnew = True
        except pymongo.errors.DuplicateKeyError:
            session(r).expunge(r)
            r = cls.query.get(object_id=object_id)
        return r, isnew

    def set_last_commit(self, ci, repo=None):
        '''Update the last_commit_for object based on the passed in commit &
        repo'''
        if repo is None: repo = pylons.c.app.repo
        lc, isnew = LastCommitFor.upsert(repo_id=repo._id, object_id=self.object_id)
        if isnew:
            lc.last_commit.author = ci.authored.name
            lc.last_commit.author_email = ci.authored.email
            lc.last_commit.author_url = ci.author_url
            lc.last_commit.date = ci.authored.date
            lc.last_commit.id = ci.object_id
            lc.last_commit.href = ci.url()
            lc.last_commit.shortlink = ci.shorthand_id()
            lc.last_commit.summary = ci.summary
            assert lc.last_commit.date
        return lc, isnew

    def get_last_commit(self, repo=None):
        if repo is None: repo = pylons.c.app.repo
        lc = LastCommitFor.query.get(
            repo_id=repo._id, object_id=self.object_id)
        return lc.last_commit

    def __repr__(self):
        return '<%s %s>' % (
            self.__class__.__name__, self.object_id)

    def index_id(self):
        return repr(self)

    def set_context(self, context):
        '''Set ephemeral (unsaved) attributes based on a context object'''
        raise NotImplementedError, 'set_context'

    def primary(self): return self

class LogCache(RepoObject):
    '''Class to store nothing but lists of commit IDs in topo sort order'''
    class __mongometa__:
        polymorphic_identity='log_cache'
    type_s = 'LogCache'

    type = FieldProperty(str, if_missing='log_cache')
    object_ids = FieldProperty([str])
    candidates = FieldProperty([str])

    @classmethod
    def get(cls, repo, object_id):
        lc, new = cls.upsert('$' + object_id)
        if not lc.object_ids:
            lc.object_ids, lc.candidates = repo._impl.log(object_id, 0, 50)
        return lc

class Commit(RepoObject):
    class __mongometa__:
        polymorphic_identity='commit'
    type_s = 'Commit'

    # File data
    type = FieldProperty(str, if_missing='commit')
    tree_id = FieldProperty(str)
    diffs = FieldProperty(dict(
            added=[str],
            removed=[str],
            changed=[str],
            copied=[dict(old=str, new=str)]))
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

    @LazyProperty
    def author_url(self):
        u = User.by_email_address(self.authored.email)
        if u: return u.url()

    @LazyProperty
    def committer_url(self):
        u = User.by_email_address(self.committed.email)
        if u: return u.url()

    @LazyProperty
    def tree(self):
        t = Tree.query.get(object_id=self.tree_id)
        t.set_context(self)
        return t

    @LazyProperty
    def summary(self):
        message = h.really_unicode(self.message)
        first_line = message.split('\n')[0]
        return h.text.truncate(first_line, 75)

    def get_path(self, path):
        '''Return the blob on the given path'''
        if path.startswith('/'): path = path[1:]
        path_parts = path.split('/')
        return self.tree.get_blob(path_parts[-1], path_parts[:-1])

    def shorthand_id(self):
        return self.repo.shorthand_for_commit(self)

    def url(self):
        return self.repo.url_for_commit(self)

    def dump_ref(self):
        return CommitReference(
            commit_class=self.__class__,
            object_id=self.object_id)

    def log(self, skip, count):
        oids = list(self.log_iter(skip, count))
        commits = self.query.find(dict(
                type='commit',
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
            seen_oids.update(lc.object_ids)
            candidates += lc.candidates
        return len(seen_oids)

    def compute_diffs(self, seen_objects):
        self.diffs.added = []
        self.diffs.removed = []
        self.diffs.changed = []
        self.diffs.copied = []
        if self.parent_ids:
            parent = self.repo.commit(self.parent_ids[0])
            for diff in Tree.diff(parent.tree, self.tree, seen_objects):
                if diff.is_new:
                    self.diffs.added.append(diff.b_path)
                    obj = RepoObject.query.get(object_id=diff.b_object_id)
                    obj.set_last_commit(self)
                elif diff.is_delete:
                    self.diffs.removed.append(diff.a_path)
                elif diff.is_copy:
                    self.diffs.copied.append(dict(
                            old=diff.a_path, new=diff.b_path))
                    obj = RepoObject.query.get(object_id=diff.b_object_id)
                    obj.set_last_commit(self)
                else:
                    self.diffs.changed.append(diff.a_path)
                    obj = RepoObject.query.get(object_id=diff.b_object_id)
                    obj.set_last_commit(self)
        else:
            # Parent-less, so the whole tree is additions
            tree = self.tree
            for oid, name in tree.object_ids.items():
                self.diffs.added.append('/'+name)
                obj = RepoObject.query.get(oid)
                obj.set_last_commit(self)

    def context(self):
        return self.repo.commit_context(self)

class Tree(RepoObject):
    README_NAMES=set(['readme.txt','README.txt','README.TXT','README'])
    class __mongometa__:
        polymorphic_identity='tree'
    type_s = 'Tree'

    type = FieldProperty(str, if_missing='tree')
    object_ids = FieldProperty({str:str}) # objects[oid] = name

    def __init__(self, **kw):
        super(Tree, self).__init__(**kw)
        # Ephemeral attrs
        self.repo = None
        self.commit = None
        self.parent = None
        self.name = None

    def compute_hash(self):
        '''Compute a hash based on the contents of the tree.  Note that this
        hash does not necessarily correspond to any actual DVCS hash.
        '''
        lines = [('t' + oid + name) for oid, name in self.trees.iteritems() ]
        lines += [('b' + oid + name) for oid, name in self.trees.iteritems() ]
        sha_obj = sha1()
        for line in sorted(lines):
            sha_obj.update(line)
        return sha_obj.hexdigest()

    def set_last_commit(self, ci, repo=None):
        lc, isnew = super(Tree, self).set_last_commit(ci, repo)
        if isnew:
            for oid in self.object_ids:
                obj = RepoObject.query.get(object_id=oid)
                obj.set_last_commit(ci, repo)
        return lc, isnew
        
    @LazyProperty
    def objects(self):
        objects = RepoObject.query.find(dict(
                object_id={'$in':self.object_ids.keys()})).all()
        for o in objects:
            o.set_context(self, self.object_ids[o.object_id])
        return objects

    @LazyProperty
    def trees(self):
        return [ o for o in self.objects if isinstance(o, Tree) ]

    @LazyProperty
    def blobs(self):
        return [ o for o in self.objects if isinstance(o, Blob) ]

    @LazyProperty
    def object_index(self):
        return dict((o.name, o) for o in self.objects)

    @LazyProperty
    def object_id_index(self):
        return dict((name, oid) for oid,name in self.object_ids.iteritems())

    def get(self, name, default=None):
        return self.object_index.get(name, default)

    def __getitem__(self, name):
        return self.object_index[name]

    @classmethod
    def diff(cls, a, b, seen_objects):
        '''Recursive diff of two tree objects, yielding DiffObjects'''
        if not isinstance(a, Tree) or not isinstance(b, Tree):
            yield DiffObject(a, b)
        else:
            for a_oid, a_name in a.object_ids.iteritems():
                b_oid = b.object_id_index.get(a_name)
                if a_oid == b_oid: continue
                a_obj = seen_objects.get(a_oid)
                b_obj = seen_objects.get(b_oid)
                if a_obj is None: a_obj = seen_objects[a_oid] = a.get(a_name)
                if b_obj is None: b_obj = seen_objects[b_oid] = b.get(a_name)
                if b_obj is None:
                    yield DiffObject(a_obj, None)
                else:
                    for x in cls.diff(a_obj, b_obj, seen_objects): yield x
            for b_oid, b_name in b.object_ids.iteritems():
                if b_name in a.object_id_index: continue
                b_obj = seen_objects[b_oid] = b.get(b_name)
                yield DiffObject(None, b_obj)

    def set_context(self, commit_or_tree, name=None):
        assert commit_or_tree is not self
        self.repo = commit_or_tree.repo
        if name:
            self.commit = commit_or_tree.commit
            self.parent = commit_or_tree
            self.name = name
        else:
            self.commit = commit_or_tree

    def readme(self):
        for name in self.object_ids:
            if self.object_ids[name] in self.README_NAMES:
                blob = self.get_blob(self.object_ids[name])
                return h.really_unicode(blob.text)
        return ''

    def ls(self):
        for obj in sorted(self.trees, key=lambda o:o.name):
            ci = obj.get_last_commit()
            yield dict(kind='DIR',
                       last_commit=ci,
                       name=obj.name,
                       href=obj.name + '/')
        for obj in sorted(self.blobs, key=lambda o:o.name):
            if obj.name == '.': continue
            ci = obj.get_last_commit()
            yield dict(kind='FILE',
                       last_commit=ci,
                       name=obj.name,
                       href=obj.name)

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

    def is_blob(self, name):
        obj = RepoObject.query.get(
            object_id=self.object_id_index[name])
        return isinstance(obj, Blob)

    def get_tree(self, name):
        t = self.get(name)
        if isinstance(t, Tree): return t
        return None

    def get_blob(self, name, path_parts=None):
        if path_parts:
            t = self.get_tree(path_parts[0])
            if t:
                return t.get_blob(name, path_parts[1:])
            else:
                return None
        b = self.get(name)
        if isinstance(b, Blob): return b
        return None

class Blob(RepoObject):
    class __mongometa__:
        polymorphic_identity='blob'
    type_s = 'Blob'

    type = FieldProperty(str, if_missing='blob')

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

    @LazyProperty
    def prev_commit(self):
        lc = self.get_last_commit()
        if lc.id:
            last_commit = self.repo.commit(lc.id)
            if last_commit.parent_ids:
                return self.repo.commit(last_commit.parent_ids[0])
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
        path = self.path()[1:]
        prev = self.prev_commit
        next = self.next_commit
        if prev is not None: prev = prev.get_path(path)
        if next is not None: next = next.get_path(path)
        return dict(
            prev=prev,
            next=next)

    def compute_hash(self):
        '''Compute a hash based on the contents of the blob.  Note that this
        hash does not necessarily correspond to any actual DVCS hash.
        '''
        fp = self.open()
        sha_obj = sha1()
        while True:
            buffer = fp.read(4096)
            if not buffer: break
            sha_obj.update(buffer)
        return sha_obj.hexdigest()

    def open(self):
        return self.repo.open_blob(self)

    def __iter__(self):
        return iter(self.open())

    @LazyProperty
    def text(self):
        return self.open().read()

    @classmethod
    def diff(cls, v0, v1):
        differ = SequenceMatcher(v0, v1)
        return differ.get_opcodes()

class CommitReference(object):
    def __init__(self, commit_class, commit_id):
        self.commit_class = commit_class
        self.commit_id = commit_id

    @property
    def artifact(self):
        return self.commit_class.query.get(
            commit_id=self.commit_id)

class DiffObject(object):
    a_path = b_path = None
    a_object_id = b_object_id = None
    is_new = False
    is_delete = False
    is_copy = False

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
            self.is_delete = True

    def __repr__(self):
        if self.is_new:
            return '<new %s>' % self.b_path
        elif self.is_delete:
            return '<remove %s>' % self.a_path
        elif self.is_copy:
            return '<copy %s to %s>' % (
                self.a_path, self.b_path)
        else:
            return '<change %s>' % (self.a_path)

class GitLikeTree(object):
    '''A tree node similar to that which is used in git'''

    def __init__(self):
        self.blobs = {}  # blobs[name] = oid
        self.trees = defaultdict(GitLikeTree) #trees[name] = GitLikeTree()
        self._hex = None

    @classmethod
    def from_tree(cls, tree):
        self = GitLikeTree()
        for o in tree.blobs:
            self.blobs[o.name] = o.object_id
        for o in tree.trees:
            subtree = Tree.query.get(object_id=o.object_id)
            self.trees[o.name] = GitLikeTree.from_tree(subtree)
        return self

    def set_blob(self, path, oid):
        if path.startswith('/'): path = path[1:]
        path_parts = path.split('/')
        dirpath, filename = path_parts[:-1], path_parts[-1]
        cur = self
        for part in dirpath:
            cur = cur.trees[part]
        cur.blobs[filename] = oid

    def del_blob(self, path):
        if path.startswith('/'): path = path[1:]
        path_parts = path.split('/')
        dirpath, filename = path_parts[:-1], path_parts[-1]
        cur = self
        for part in dirpath:
            cur = cur.trees[part]
        if filename in cur.trees:
            cur.trees.pop(filename, None)
        else:
            cur.blobs.pop(filename, None)

    def hex(self):
        '''Compute a recursive sha1 hash on the tree'''
        if self._hex is None:
            sha_obj = sha1('tree\n' + repr(self))
            self._hex = sha_obj.hexdigest()
        return self._hex

    def __repr__(self):
        lines = [('t %s %s' % (t.hex(), name))
                  for name, t in self.trees.iteritems() ]
        lines += [('b %s %s' % (oid, name))
                  for name, oid in self.blobs.iteritems() ]
        return '\n'.join(sorted(lines))

def topological_sort(graph):
    '''Return the topological sort of a graph.

    The graph is a dict with each entry representing
    a node (the key is the node ID) and its parent(s) (a
    set of node IDs). Result is an iterator over the topo-sorted
    node IDs.

    The algorithm is based on one seen in
    http://en.wikipedia.org/wiki/Topological_sorting#CITEREFKahn1962
    '''
    # Index children, identify roots
    children = defaultdict(list)
    roots = []
    for nid, parents in graph.items():
        if not parents:
            graph.pop(nid)
            roots.append(nid)
        for p_nid in parents: children[p_nid].append(nid)
    # Topo sort
    while roots:
        n = roots.pop()
        yield n
        for child in children[n]:
            graph[child].remove(n)
            if not graph[child]:
                graph.pop(child)
                roots.append(child)
    assert not graph, 'Cycle detected'

MappedClass.compile_all()
