import os
import cPickle as pickle
import email as EM
from datetime import datetime

import pymongo
from pylons import c
from mercurial import ui, hg

from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty
from ming.utils import LazyProperty

from pyforge.model import Repository, ArtifactReference
from pyforge.lib import helpers as h

class HgRepository(Repository):
    class __mongometa__:
        name='hg-repository'

    def index(self):
        result = Repository.index(self)
        result.update(
            type_s='HgRepository')
        return result

    @LazyProperty
    def _impl(self):
        return hg.repository(ui.ui(), os.path.join(c.app.repo.path, c.app.repo.name))

    def __iter__(self):
        cs = self._impl[self._impl.heads()[0]]
        return self.iter_changeset(cs)

    def iter_changeset(self, changeset):
        yield HgCommit.from_hg(changeset, self)
        for x in changeset.ancestors():
            yield HgCommit.from_hg(x, self)

    def iter_branch(self, branch):
        branch = self._impl.branchmap().get(branch, [])
        if branch:
            return self.iter_changeset(self._impl[branch[0]])
        else:
            return []

    def iter_tag(self, tag):
        tag = self._impl.tags().get(tag)
        if tag:
            return self.iter_changeset(self._impl[tag])
        else:
            return []

    def __getattr__(self, name):
        return getattr(self._impl, name)

    def __getitem__(self, name):
        return HgCommit.from_hg(self._impl[name], self)

    @property
    def tags(self):
        '''Override Artifact.tags'''
        return self._impl.tags

class HgCommit(object):
    type_s='HgCommit'

    def __init__(self, id, repo):
        self._id = id
        self._repo = repo

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

    def dump_ref(self):
        '''Return a pickle-serializable reference to an artifact'''
        try:
            d = ArtifactReference(dict(
                    project_id=c.project._id,
                    mount_point=c.app.config.options.mount_point,
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

    def parents(self):
        return tuple(HgCommit.from_hg(c, self._repo) for c in self._impl.parents())

    @property
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
