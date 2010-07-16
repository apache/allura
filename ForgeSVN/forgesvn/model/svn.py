import os
import errno
import stat
import logging
import subprocess
import cPickle as pickle
from cStringIO import StringIO
from datetime import datetime

import pysvn
import pymongo
from pylons import c

from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty
from ming.utils import LazyProperty

from pyforge import model as M

log = logging.getLogger(__name__)

def on_import():
    SVNRepository.CommitClass = SVNCommit
    SVNCommit.TreeClass = SVNTree
    SVNTree.BlobClass = SVNBlob

class SVNRepository(M.Repository):
    MAGIC_FILENAME='.SOURCEFORGE-REPOSITORY'
    class __mongometa__:
        name='svn-repository'

    def index(self):
        result = super(SVNRepository, self).index()
        result.update(
            type_s='SVNRepository')
        return result

    @LazyProperty
    def _impl(self):
        return pysvn.Client()

    @LazyProperty
    def local_url(self):
        return 'file://%s/%s' % (self.fs_path, self.name)

    @LazyProperty
    def last_revision(self):
        info = self._impl.info2(
            self.local_url,
            revision=pysvn.Revision(pysvn.opt_revision_kind.head),
            recurse=False)
        return info[0][1].rev.number

    def init(self):
        if not self.fs_path.endswith('/'): self.fs_path += '/'
        try:
            os.makedirs(self.fs_path)
        except OSError, e: # pragma no cover
            if e.errno != errno.EEXIST: raise
        # We may eventually require --template=...
        log.info('svnadmin create %s%s', self.fs_path, self.name)
        result = subprocess.call(['svnadmin', 'create', self.name],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 cwd=self.fs_path)
        magic_file = os.path.join(self.fs_path, self.name, self.MAGIC_FILENAME)
        with open(magic_file, 'w') as f:
            f.write('svn')
        os.chmod(magic_file, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
        self.status = 'ready'

    def _log(self, url, **kwargs):
        try:
            offset = kwargs.pop('offset', 0)
            limit=kwargs.get('limit', 10)
            if offset != 0:
                latest = self._impl.log(url, limit=1)
                if not latest: return []
                latest = latest[0]
                revno = latest.revision.number-offset
                if offset + limit > revno:
                    limit = revno - offset
                if limit <= 0: return []
                revno = max(revno, 0)
                kwargs['revision_start'] = pysvn.Revision(
                        pysvn.opt_revision_kind.number,
                        revno)
            commits = self._impl.log(url, **kwargs)
            return [ self.CommitClass.from_repo_object(entry, self) for entry in commits ]
        except pysvn.ClientError: # pragma no cover
            # probably an empty repo
            return []
        except:  # pragma no cover
            log.exception('Error performing SVN log:')
            return []

    def log(self, branch=None, offset=0, limit=10):
        return self._log(self.local_url, offset=offset, limit=limit)

    @LazyProperty
    def latest(self):
        try:
            l = self._impl.log(self.local_url, limit=1)
        except pysvn.ClientError:
            return None
        if l:
            return self.CommitClass.from_repo_object(l[0], self)
        else:
            return None

    def commit(self, revision):
        try:
            r = self._impl.log(
                self.local_url,
                revision_start=pysvn.Revision(
                    pysvn.opt_revision_kind.number, revision),
                limit=1)
        except pysvn.ClientError:
            return None
        if r: return self.CommitClass.from_repo_object(r[0], self)
        else: return None

    # def diff(self, r0, r1):
    #     r0 = pysvn.Revision(pysvn.opt_revision_kind.number, r0)
    #     r1 = pysvn.Revision(pysvn.opt_revision_kind.number, r1)
    #     return self._impl.diff(
    #         '/tmp', self.local_url, r0,
    #         self.local_url, r1)

    def diff_summarize(self, r0, r1):
        r0 = pysvn.Revision(pysvn.opt_revision_kind.number, r0)
        r1 = pysvn.Revision(pysvn.opt_revision_kind.number, r1)
        result = self._impl.diff_summarize(
            self.local_url, r0,
            self.local_url, r1)
        return result

class SVNCommit(M.Commit):
    type_s='SvnCommit'

    @classmethod
    def from_repo_object(cls, entry, repo):
        result = cls(id=entry.revision.number, repo=repo)
        result.__dict__['_impl'] = entry
        result.author_username=entry.get('author')
        result.datetime=datetime.utcfromtimestamp(entry.date)
        return result

    @LazyProperty
    def revision(self):
        return pysvn.Revision(pysvn.opt_revision_kind.number, self._id)

    def context(self):
        prev = next = None
        if self.revision.number < self._repo.latest.revision.number:
            next = self._repo.commit(self.revision.number+1)
        if self.revision.number > 1:
            prev = self._repo.commit(self.revision.number-1)
        return dict(prev=prev, next=next)

    def __getattr__(self, name):
        return getattr(self._impl, name)

    def dump_ref(self):
        '''Return a pickle-serializable reference to an artifact'''
        try:
            d = M.ArtifactReference(dict(
                    project_id=c.project._id,
                    mount_point=c.app.config.options.mount_point,
                    artifact_type=pymongo.bson.Binary(pickle.dumps(self.__class__)),
                    artifact_id=self._id))
            return d
        except AttributeError: # pragma no cover
            return None

    def url(self):
        return self._repo.url() + str(self._id) + '/'

    def primary(self, *args):
        return self

    def shorthand_id(self):
        return '[r%s]' % self._id

    def diff_summarize(self, other_rev=None):
        if other_rev is None: other_rev = self._id-1
        for s in self._repo.diff_summarize(other_rev, self._id):
            yield str(s.summarize_kind), s.path

    # def diff(self, other_rev=None):
    #     if other_rev is None: other_rev = self._id-1
    #     return super(SVNCommit, self).diff(other_rev)

    @LazyProperty
    def author(self):
        return M.User.by_username(self.author_username)

class SVNTree(M.Tree):

    def ls(self):
        try:
            for dirent in self._repo._impl.ls(
                self._repo.local_url + self.path(),
                revision=self._commit.revision):
                name = dirent.name.rsplit('/')[-1]
                date = datetime.fromtimestamp(dirent.time)
                href = name
                if dirent.kind == pysvn.node_kind.dir:
                    href = href + '/'
                commit = self._repo.commit(dirent.created_rev.number)
                yield dict(dirent, name=name, date=date, href=href,
                           commit=commit)
        except pysvn.ClientError:
            pass

    def is_blob(self, name):
        dirent = self._repo._impl.ls(
            self._repo.local_url + self.path()+name,
            revision=self._commit.revision)
        if len(dirent) != 1: return False
        dirent = dirent[0]
        if dirent.kind == pysvn.node_kind.file:
            return True
        return False

class SVNBlob(M.Blob):

    def __iter__(self):
        fp = StringIO(self.text)
        return iter(fp)

    @LazyProperty
    def text(self):
        return self._repo._impl.cat(
            self._repo.local_url + self.path(),
            revision=self._commit.revision)

    def context(self):
        entries = self._repo._log(self._repo.local_url + self.path())
        result = dict(prev=None, next=None)
        path = self._tree.path().split('/')[1:-1]
        prev=next=None
        for ent in entries:
            if ent.revision.number < self._commit.revision.number:
                prev=ent
                break
            if ent.revision.number > self._commit.revision.number:
                next=ent
        if prev:
            ci = SVNCommit.from_repo_object(prev, self._repo)
            result['prev'] = ci.tree().get_blob(self.filename, path)
        if next:
            ci = SVNCommit.from_repo_object(next, self._repo)
            result['next'] = ci.tree().get_blob(self.filename, path)
        return result

on_import()
MappedClass.compile_all()
