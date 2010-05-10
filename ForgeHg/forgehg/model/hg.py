import os
import stat
import errno
import logging
import subprocess
import cPickle as pickle
import email as EM
from datetime import datetime

import pymongo
from pylons import c
from mercurial import ui, hg

from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty
from ming.utils import LazyProperty

from pyforge.model import Repository, Commit, ArtifactReference
from pyforge.lib import helpers as h

log = logging.getLogger(__name__)

class HgRepository(Repository):
    class __mongometa__:
        name='hg-repository'

    def index(self):
        result = Repository.index(self)
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
                                 cwd=self.fs_path)
        self._setup_special_files()
        self.status = 'ready'

    def init_as_clone(self, source_path):
        self._setup_paths()
        log.info('hg clone %s %s%s' % (source_path, self.fs_path, self.name))
        result = subprocess.call(['hg', 'clone', '--noupdate', source_path, self.name],
                                 cwd=self.fs_path)
        # How do we want to handle merge-requests?  Will it be in repo?
        self._setup_special_files()
        self.status = 'ready'

    @LazyProperty
    def _impl(self):
        return hg.repository(ui.ui(), os.path.join(self.fs_path, self.name))

    def __iter__(self):
        return self.log()

    def revision(self, hash):
        return HgCommit.from_hg(self._impl[hash], self)

    def log(self, changeset=None, branch=None, tag=None):
        if branch and branch in self._impl.branchmap():
            cs = self._impl.branchmap()[branch][0]
        elif tag and tag in self._impl.tags():
            cs = self._impl.tags()[tag]
        elif changeset:
            cs = changeset
        else:
            cs = self._impl.heads()[0]
        cs = self._impl[cs]
        yield HgCommit.from_hg(cs, self)
        for x in cs.ancestors():
            yield HgCommit.from_hg(x, self)

    def __getattr__(self, name):
        return getattr(self._impl, name)

    def __getitem__(self, name):
        return HgCommit.from_hg(self._impl[name], self)

    def repo_tags(self):
        '''Override Artifact.tags'''
        return self._impl.tags()

class HgCommit(Commit):
    type_s='HgCommit'

    @classmethod
    def from_hg(cls, ctx ,repo):
        result = cls(id=ctx.hex(), repo=repo)
        result.__dict__['_impl'] = ctx
        result.user = dict(
            name=EM.utils.parseaddr(ctx.user())[0],
            email=EM.utils.parseaddr(ctx.user())[1])
        result.user_url = None
        result.revision=ctx.rev()
        result.datetime=datetime.fromtimestamp(sum(ctx.date()))
        return result

    def __getattr__(self, name):
        return getattr(self._impl, name)

    def shorthand_id(self):
        return '[%s]' % self._id[:6]

    def parents(self):
        return tuple(HgCommit.from_hg(p, self._repo)
                     for p in self._impl.parents())

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

MappedClass.compile_all()
