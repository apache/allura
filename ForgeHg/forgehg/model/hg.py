import os
os.environ['HGRCPATH'] = '' # disable loading .hgrc
import stat
import errno
import logging
import subprocess
import cPickle as pickle
import email as EM
from datetime import datetime
from cStringIO import StringIO
from itertools import islice

import pymongo
from pylons import c
from mercurial import ui, hg
from webob import exc

from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty
from ming.utils import LazyProperty

from allura import model as M
from allura.lib import helpers as h

log = logging.getLogger(__name__)

def on_import():
    HgRepository.CommitClass = HgCommit
    HgCommit.TreeClass = HgTree
    HgTree.BlobClass = HgBlob

class HgRepository(M.Repository):
    class __mongometa__:
        name='hg-repository'

    def index(self):
        result = super(HgRepository, self).index()
        result.update(
            type_s='HgRepository')
        return result

    def _setup_paths(self):
        if not self.fs_path.endswith('/'): self.fs_path += '/'
        try:
            os.makedirs(self.fs_path)
        except OSError, e: # pragma no cover
            if e.errno != errno.EEXIST:
                raise

    def _setup_special_files(self):
        magic_file = os.path.join(self.full_fs_path, '.SOURCEFORGE-REPOSITORY')
        with open(magic_file, 'w') as f:
            f.write('hg')
        os.chmod(magic_file, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
        # TO DO: set up equivalent of receive-hook here

    def init(self):
        self._setup_paths()
        # We may eventually require --template=...
        log.info('hg init %s', self.full_fs_path)
        result = subprocess.call(['hg', 'init', self.name],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 cwd=self.fs_path)
        self._setup_special_files()
        self.status = 'ready'

    def init_as_clone(self, source_path):
        self._setup_paths()
        log.info('hg clone %s %s%s' % (source_path, self.fs_path, self.name))
        result = subprocess.call(['hg', 'clone', '--noupdate', source_path, self.name],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 cwd=self.fs_path)
        # How do we want to handle merge-requests?  Will it be in repo?
        self._setup_special_files()
        self.status = 'ready'

    @LazyProperty
    def _impl(self):
        return hg.repository(ui.ui(), os.path.join(self.fs_path, self.name))

    def __iter__(self):
        return self.log()

    def commit(self, hash):
        return self.CommitClass.from_repo_object(self._impl[hash], self)

    def _log(self, ci, **kwargs):
        def _iter(root):
            seen = set()
            frontier = [root]
            while frontier:
                ci = frontier.pop(0)
                if ci in seen: continue
                yield ci
                seen.add(ci)
                frontier += ci.parents()
                frontier.sort(key=lambda ci: sum(ci.date()))
        commits = _iter(ci)
        offset = kwargs.pop('offset', 0)
        limit = kwargs.pop('limit', None)
        if limit is None:
            commits = islice(commits, offset, None)
        else:
            commits = islice(commits, offset, offset+limit)
        return [ self.CommitClass.from_repo_object(entry, self)
                 for entry in commits ]

    def log(self, branch=None, tag='tip', offset=0, limit=10):
        if branch is not None:
            ci = self._impl.branchmap()[branch][0]
        elif tag is not None:
            ci = self._impl.tags()[tag]
        else:
            ci = self._impl.changelog.tip()
        ci = self._impl[ci]
        return self._log(ci, offset=offset, limit=limit)

    def __getattr__(self, name):
        assert type(self._impl) != type(self)
        return getattr(self._impl, name)

    def __getitem__(self, name):
        return HgCommit.from_repo_object(self._impl[name], self)

    def repo_tags(self):
        '''Override Artifact.tags'''
        return self._impl.tags()

class HgCommit(M.Commit):
    type_s='HgCommit'
    _impl = None

    @classmethod
    def from_repo_object(cls, ctx ,repo):
        result = cls(id=ctx.hex(), repo=repo)
        result.__dict__['_impl'] = ctx
        result.user = dict(
            name=EM.utils.parseaddr(ctx.user())[0],
            email=EM.utils.parseaddr(ctx.user())[1])
        result.user_url = None
        result.revision=ctx.rev()
        result.datetime=datetime.fromtimestamp(sum(ctx.date()))
        return result

    def url(self):
        return self._repo.url() + 'ci/' + self._id + '/'

    def __getattr__(self, name):
        assert type(self._impl) != type(self)
        return getattr(self._impl, name)

    def shorthand_id(self):
        return '[%s]' % self._id[:6]

    @LazyProperty
    def parents(self):
        return tuple(HgCommit.from_repo_object(p, self._repo)
                     for p in self._impl.parents())

    @LazyProperty
    def children(self):
        return tuple(HgCommit.from_repo_object(p, self._repo)
                     for p in self._impl.children())

    def tree(self):
        return self.TreeClass(self._repo, self)

    def diffs(self):
        differ = h.diff_text_genshi
        for fn in self.changeset()[3]:
            fc = self._impl[fn]
            if fc.parents():
                a = fc.parents()[0].path()
                a_text = fc.parents()[0].data()
            else:
                a = '<<null>>'
                a_text = ''
            yield (
                a, fc.path(), ''.join(differ(a_text, fc.data())))
        else:
            pass

    def diff_summarize(self):
        if len(self.parents) == 1:
            parent = self.parents[0]
            for filename in self._impl.files():
                if filename in parent._impl:
                    if filename in self._impl:
                        yield 'change', filename
                    else:
                        yield 'remove', filename
                else:
                    yield 'add', filename
        elif len(self.parents) == 0:
            for filename in self._impl.files():
                yield 'add', filename

    def context(self):
        return dict(
            prev=self.parents,
            next=self.children)

class HgTree(M.Tree):

    def __init__(self, repo, commit, parent=None, name=None):
        super(HgTree, self).__init__(repo, commit, parent, name)
        if self._parent:
            self._tree = self._parent._tree[name]
            self._manifest = self._parent._manifest
        else:
            self._tree = {}
            self._manifest = commit._manifest
            for k,v in self._manifest.iteritems():
                dirname, filename = os.path.split(k)
                tree = self._tree
                for dirpart in dirname.split('/'):
                    tree = tree.setdefault(dirpart, {})
                tree[filename] = v

    def ls(self):
        for name, dirent in sorted(self._tree.iteritems()):
            name = name
            date = None
            href = name
            last_author = '-'
            commit = None
            if isinstance(dirent, dict):
                href = href + '/'
                kind='dir'
            else:
                kind='file'
                fc = self._repo._impl.filectx(
                    self.path() + name,
                    fileid=dirent)
                date = datetime.fromtimestamp(sum(fc.date()))
                last_author = fc.user()
                commit = HgCommit.from_repo_object(fc.changectx(), self._repo)
            yield dict(
                dirent=dirent,
                name=name,
                date=date,
                href=href,
                kind=kind,
                last_author=last_author,
                commit=commit,
                )

    def is_blob(self, name):
        try:
            dirent = self._tree[name]
            return not isinstance(dirent, dict)
        except:
            log.exception('Error checking blob-ness of %s', name)
            return False

class HgBlob(M.Blob):

    def __init__(self, repo, commit, tree, filename):
        super(HgBlob, self).__init__(
            repo, commit, tree, filename)
        self._blob = self._repo._impl.filectx(
            self.path(), fileid=tree._tree[filename])

    def __iter__(self):
        fp = StringIO(self.text)
        return iter(fp)

    @LazyProperty
    def text(self):
        return self._blob.data()

    @classmethod
    def from_repo_object(cls, fc, repo):
        ci = HgCommit.from_repo_object(fc.changectx(), repo)
        dirname, filename = os.path.split(fc.path())
        tree = ci.tree()
        try:
            return tree.get_blob(filename, dirname[1:].split('/'))
        except KeyError:
            return None

    def context(self):
        prev=[ HgBlob.from_repo_object(fc, self._repo)
               for fc in self._blob.parents() ]
        next=[ HgBlob.from_repo_object(fc, self._repo)
               for fc in self._blob.children() ]
        prev = [ b for b in prev if b is not None ]
        next = [ b for b in next if b is not None ]
        return dict(prev=prev, next=next)

    def __getattr__(self, name):
        return getattr(self._blob, name)

on_import()
MappedClass.compile_all()
