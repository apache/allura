import os
import sys
import stat
import errno
import logging
import subprocess
import pkg_resources
from itertools import islice
import cPickle as pickle
from datetime import datetime

import git
import pylons
import pymongo.bson

from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty
from ming.utils import LazyProperty

from pyforge.model import Repository, ArtifactReference, User
from pyforge.lib import helpers as h

log = logging.getLogger(__name__)

class GitRepository(Repository):
    class __mongometa__:
        name='git-repository'

    def index(self):
        result = Repository.index(self)
        result.update(
            type_s='GitRepository')
        return result

    def init(self):
        if not self.fs_path.endswith('/'): self.fs_path += '/'
        fullname = os.path.join(self.fs_path, self.name)
        try:
            os.makedirs(fullname)
        except OSError, e: # pragma no cover
            if e.errno != errno.EEXIST: raise
        log.info('git init %s', fullname)
        result = subprocess.call(['git', 'init', '--bare', '--shared=all'],
                                 cwd=fullname)
        magic_file = os.path.join(fullname, '.SOURCEFORGE-REPOSITORY')
        with open(magic_file, 'w') as f:
            f.write('git')
        os.chmod(magic_file, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)
        self._setup_receive_hook(
            pylons.c.app.config.script_name())
        self.status = 'ready'

    def revision(self, rev):
        return GitCommit(rev, self)

    def log(self, *args, **kwargs):
        return (GitCommit.from_git(c, self)
                for c in self._impl.iter_commits(*args, **kwargs))

    @LazyProperty
    def _impl(self):
        return git.Repo(os.path.join(self.fs_path, self.name))

    def __getattr__(self, name):
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
        fn = os.path.join(os.path.join(self.fs_path, self.name), 'hooks', 'post-receive')
        with open(fn, 'w') as fp:
            fp.write(text)
        os.chmod(fn, 0755)

class MockQuery(object):
    def __init__(self, cls):
        self._cls = cls

    def get(self, _id):
        return self._cls(_id, repo=pylons.c.app.repo)

class GitCommit(object):
    type_s='GitCommit'

    def __init__(self, id, repo):
        self._id = id
        self._repo = repo

    @classmethod
    def from_git(cls, c, repo):
        result = cls(id=c.sha, repo=repo)
        result.__dict__['_impl'] = c
        return result

    def dump_ref(self):
        '''Return a pickle-serializable reference to an artifact'''
        try:
            d = ArtifactReference(dict(
                    project_id=pylons.c.project._id,
                    mount_point=pylons.c.app.config.options.mount_point,
                    artifact_type=pymongo.bson.Binary(pickle.dumps(self.__class__)),
                    artifact_id=self._id))
            return d
        except AttributeError:
            return None

    def url(self):
        return self._repo.url() + self._id

    def primary(self, *args):
        return self

    def shorthand_id(self):
        return '[%s]' % self._id[:6]

    @LazyProperty
    def _impl(self):
        return self._repo._impl.commit(self._id)

    def __getattr__(self, name):
        return getattr(self._impl, name)

    @LazyProperty
    def authored_datetime(self):
        return datetime.fromtimestamp(self.authored_date+self.author_tz_offset)

    @LazyProperty
    def committed_datetime(self):
        return datetime.fromtimestamp(self.authored_date+self.author_tz_offset)

    @LazyProperty
    def author_url(self):
        u = User.by_email_address(self.author.email)
        if u: return u.url()

    @LazyProperty
    def committer_url(self):
        u = User.by_email_address(self.committer.email)
        if u: return u.url()

    @LazyProperty
    def parents(self):
        return tuple(GitCommit.from_git(c, self._repo) for c in self._impl.parents)

    @property
    def diffs(self):
        if self.parents:
            differ = h.diff_text_genshi
            for d in self._impl.diff(self.parents[0].sha):
                yield (
                    d.a_blob,
                    d.b_blob,
                    ''.join(differ(d.a_blob.data, d.b_blob.data)))
        else:
            pass

GitCommit.query = MockQuery(GitCommit)

MappedClass.compile_all()
