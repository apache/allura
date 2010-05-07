import os
import cPickle as pickle

import pylons
import pymongo.bson

from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty

from .artifact import Artifact
from .types import ArtifactReference

class Repository(Artifact):
    class __mongometa__:
        name='generic-repository'

    name=FieldProperty(str)
    tool=FieldProperty(str)
    fs_path=FieldProperty(str)
    url_path=FieldProperty(str)
    status=FieldProperty(str)
    email_address=''

    def url(self):
        return self.app_config.url()

    def shorthand_id(self):
        return self.name

    def index(self):
        result = Artifact.index(self)
        result.update(
            name_s=self.name)
        return result

    @property
    def full_fs_path(self):
        return os.path.join(self.fs_path, self.name)

    def init(self):
        raise NotImplementedError, 'init'

class MockQuery(object):
    def __init__(self, cls):
        self._cls = cls

    def get(self, _id):
        return self._cls(_id, repo=pylons.c.app.repo)

class Commit(object):
    type_s='Generic Commit'

    class __metaclass__(type):
         def __new__(meta, name, bases, dct):
             result = type.__new__(meta, name, bases, dct)
             result.query = MockQuery(result)
             return result

    def __init__(self, id, repo):
        self._id = id
        self._repo = repo

    def dump_ref(self):
        '''Return a pickle-serializable reference to an artifact'''
        try:
            d = ArtifactReference(dict(
                    project_id=self._repo.project_id,
                    mount_point=self._repo.app_config.options.mount_point,
                    artifact_type=pymongo.bson.Binary(pickle.dumps(self.__class__)),
                    artifact_id=self._id))
            return d
        except AttributeError: # pragma no cover
            return None

    def url(self):
        return self._repo.url() + self._id

    def primary(self, *args):
        return self

    def shorthand_id(self):
        raise NotImplementedError, 'shorthand_id'

MappedClass.compile_all()
