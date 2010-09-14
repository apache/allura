import os
import shutil
import sys
import stat
import errno
import logging
import subprocess
import pkg_resources
import cPickle as pickle
from itertools import islice
from datetime import datetime
from cStringIO import StringIO

import tg
import git
import pylons
import pymongo.bson
from webob import exc

from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty
from ming.utils import LazyProperty

from allura import model as M
from allura.lib import helpers as h

log = logging.getLogger(__name__)

def on_import():
    GitRepository.CommitClass = GitCommit
    GitCommit.TreeClass = GitTree
    GitTree.BlobClass = GitBlob

class GitRepository(M.Repository):
    class __mongometa__:
        name='git-repository'

    def index(self):
        result = super(GitRepository, self).index()
        result.update(
            type_s='GitRepository')
        return result

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
            f.write('git')
        os.chmod(magic_file, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
        self._setup_receive_hook(
            pylons.c.app.config.script_name())

    def commit(self, hash):
        return self.CommitClass.from_repo_object(self._impl.commit(hash), self)

    def init(self):
        fullname = self._setup_paths()
        log.info('git init %s', fullname)
        result = subprocess.call(['git', 'init', '--quiet', '--bare', '--shared=all'],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 cwd=fullname)
        self._setup_special_files()
        self.status = 'ready'

    def init_as_clone(self, source_path):
        """Make this new repo be a clone of the one at source_path.

        Note that this is the opposite "direction" of git.Repo.clone().
        """
        fullname = self._setup_paths(create_repo_dir=False)
        log.info('git clone %s %s' % (source_path, fullname))
        # We may eventually require --template=...
        result = subprocess.call(['git', 'clone', '--bare', source_path, self.name],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 cwd=self.fs_path)
        # we don't want merge requests from the originating repo,
        # but local clones by default copy everything under the refs directory
        # so delete refs/requests (our custom place for storing refs) by hand
        requests = os.path.join(fullname, 'refs', 'requests')
        shutil.rmtree(requests, ignore_errors=True)
        self._setup_special_files()
        self.status = 'ready'

    def _log(self, **kwargs):
        kwargs.setdefault('topo_order', True)
        if self._impl is None: return []
        commits = self._impl.iter_commits(**kwargs)
        return [ self.CommitClass.from_repo_object(entry, self)
                 for entry in commits ]

    def log(self, branch='master', offset=0, limit=10):
        return self._log(rev=branch, skip=offset, max_count=limit)

    def count(self, branch='master'):
        try:
            return self._impl.iter_commits(rev=branch).next().count()
        except StopIteration:
            return 0

    def latest(self, branch='master'):
        if self._impl is None: return None
        try:
            return self.CommitClass.from_repo_object(self._impl.commit(rev=branch), self)
        except:
            return None

    @LazyProperty
    def _impl(self):
        try:
            return git.Repo(self.full_fs_path)
        except (git.errors.NoSuchPathError, git.errors.InvalidGitRepositoryError), err:
            return None


    def __getattr__(self, name):
        assert type(self) != type(self._impl), 'Problem looking up %s' % name
        return getattr(self._impl, name)

    def repo_tags(self):
        '''Override Artifact.tags'''
        return self._impl.tags

    def _setup_receive_hook(self, plugin_id):
        'Set up the git post-commit hook'
        tpl_fn = pkg_resources.resource_filename(
            'forgegit', 'data/post-receive_tmpl')
        config = pylons.config.get('__file__')
        text = h.render_genshi_plaintext(tpl_fn,
            executable=sys.executable,
            repository=plugin_id,
            config=config)
        fn = os.path.join(self.fs_path, self.name, 'hooks', 'post-receive')
        with open(fn, 'w') as fp:
            fp.write(text)
        os.chmod(fn, 0755)

class GitCommit(M.Commit):
    type_s='GitCommit'

    @classmethod
    def from_repo_object(cls, ci, repo):
        result = cls(id=ci.hexsha, repo=repo)
        result.__dict__['_impl'] = ci
        return result

    def shorthand_id(self):
        return '[%s]' % self._id[:6]

    def url(self):
        return self._repo.url() + 'ci/' + self._id + '/'

    @LazyProperty
    def _impl(self):
        return self._repo._impl.commit(self._id)

    def __getattr__(self, name):
        return getattr(self._impl, name)

    @LazyProperty
    def authored_datetime(self):
        return datetime.fromtimestamp(self.authored_date-self.author_tz_offset)

    @LazyProperty
    def committed_datetime(self):
        return datetime.fromtimestamp(self.authored_date-self.author_tz_offset)

    @LazyProperty
    def author_url(self):
        u = M.User.by_email_address(self.author.email)
        if u: return u.url()

    @LazyProperty
    def committer_url(self):
        u = M.User.by_email_address(self.committer.email)
        if u: return u.url()

    @LazyProperty
    def parents(self):
        return tuple(GitCommit.from_repo_object(c, self._repo)
                     for c in self._impl.parents)

    def diff_summarize(self):
        if self.parents:
            for d in self.parents[0].diff(self.hexsha):
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
        prev = self.parents
        next = []
        for ci in self._repo._impl.iter_commits():
            if self._impl in ci.parents:
                next.append(self.from_repo_object(ci, self._repo))
        return dict(prev=prev, next=next)

class GitTree(M.Tree):

    def __init__(self, repo, commit, parent=None, name=None):
        super(GitTree, self).__init__(repo, commit, parent, name)
        if parent is None:
            self._tree = self._commit._impl.tree
        else:
            try:
                self._tree = self._parent._tree[name]
            except KeyError:
                raise exc.HTTPNotFound()

    def ls(self):
        for dirent in self._tree:
            name = dirent.name
            date = None
            href = name
            if isinstance(dirent, git.Tree):
                href = href + '/'
                kind='dir'
            else:
                kind='file'
            yield dict(
                dirent=dirent,
                name=name,
                date=date,
                href=href,
                kind=kind,
                last_author='',
                commit=None,
                )

    def is_blob(self, name):
        try:
            dirent = self._tree[name]
            return isinstance(dirent, git.Blob)
        except:
            log.exception('Error checking blob-ness of %s', name)
            return False

class GitBlob(M.Blob):

    def __init__(self, repo, commit, tree, filename):
        super(GitBlob, self).__init__(
            repo, commit, tree, filename)
        try:
            self._blob = tree._tree[filename]
            self.content_type, self.content_encoding = (
                self._blob.mime_type, None)
        except KeyError:
            self._blob = None
            self.content_type = None
            self.content_encoding = None

    def __iter__(self):
        fp = StringIO(self.text)
        return iter(fp)

    @LazyProperty
    def text(self):
        return self._blob.data_stream.read()

    def context(self):
        path = self._tree.path().split('/')[1:-1]
        result = dict(prev=None, next=None)
        entries = self._repo._log(
            paths=self._blob.path)
        prev=next=None
        found_ci = False
        for ent in entries:
            if ent.hexsha == self._commit.hexsha:
                found_ci = True
            elif found_ci:
                prev=ent
                break
            elif not len(ent.context()['next']) or ent.context()['next'][0]._id != self._commit._id:
                next=ent
        if prev:
            tree = prev.tree()
            blob = tree.get_blob(self.filename, path)
            if blob._blob:
                result['prev'] = [ blob ]
        if next:
            tree = next.tree()
            blob = tree.get_blob(self.filename, path)
            if blob._blob:
                result['next'] = [ blob ]
        return result

    def __getattr__(self, name):
        return getattr(self._blob, name)

on_import()
MappedClass.compile_all()
