import logging
import cPickle as pickle
from datetime import datetime

import pysvn
import pymongo
from pylons import c

from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty
from ming.utils import LazyProperty

from pyforge.model import Repository, ArtifactReference, User
from pyforge.lib import helpers as h

log = logging.getLogger(__name__)

class SVNRepository(Repository):
    class __mongometa__:
        name='svn-repository'

    def index(self):
        result = Repository.index(self)
        result.update(
            type_s='SVNRepository')
        return result

    @LazyProperty
    def _impl(self):
        return pysvn.Client()

    @LazyProperty
    def local_url(self):
        return 'file://%s/%s' % (self.fs_path, self.name)

    def log(self, *args, **kwargs):
        try:
            return [SVNCommit.from_svn(entry, self)
                    for entry in self._impl.log(self.local_url, *args, **kwargs) ]
        except:
            log.exception('Error performing SVN log:')
            return []

    def revision(self, num):
        return self.log(
            revision_start=pysvn.Revision(
                pysvn.opt_revision_kind.number, num),
            limit=1)[0]

    def diff(self, r0, r1):
        r0 = pysvn.Revision(pysvn.opt_revision_kind.number, r0)
        r1 = pysvn.Revision(pysvn.opt_revision_kind.number, r1)
        return self._impl.diff(
            '/tmp', self.local_url, r0,
            self.local_url, r1)

class SVNCommit(object):
    type_s='SvnCommit'

    def __init__(self, id, repo):
        self._id = id
        self._repo = repo

    @classmethod
    def from_svn(cls, entry, repo):
        result = cls(id=entry.revision.number, repo=repo)
        result.__dict__['_impl'] = entry
        result.author_username=entry.author
        result.author=User.query.get(username=entry.author)
        result.datetime=datetime.utcfromtimestamp(entry.date)
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
        return self._repo.url() + str(self._id)

    def primary(self, *args):
        return self

    def shorthand_id(self):
        return '[%s]' % self._id[:6]

    def parents(self):
        return tuple(SvnCommit.from_hg(c, self._repo) for c in self._impl.parents())

    def diff(self):
        return self._repo.diff(self._id-1, self._id)


MappedClass.compile_all()
