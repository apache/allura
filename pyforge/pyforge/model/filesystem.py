import pymongo
from gridfs import GridFS

from .session import project_doc_session

from ming.base import build_mongometa

class _FilesystemMeta(type):

    def __init__(cls, name, bases, dct):
        cls.__mongometa__ = build_mongometa(bases, dct)
        cls._collection = cls.__mongometa__.name

    def ensure_indexes(cls):
        for idx in getattr(cls.__mongometa__, 'indexes', []):
            cls.ensure_index(idx)
        for idx in getattr(cls.__mongometa__, 'unique_indexes', []):
            cls.ensure_index(idx, unique=True)

    def ensure_index(cls, fields, **kwargs):
        if not isinstance(fields, (list, tuple)):
            fields = [ fields ]
        index_fields = [(f, pymongo.ASCENDING) for f in fields]
        return cls._coll.ensure_index(index_fields, **kwargs)

    @property
    def _coll(cls):
        return cls._db[cls._collection + '.files']

    @property
    def _db(cls):
        return cls.__mongometa__.session.db

    @property
    def _fs(cls):
        return GridFS(cls._db)
    
class Filesystem(object):
    __metaclass__ = _FilesystemMeta

    class __mongometa__:
        session = project_doc_session
        name = 'fs'

    @classmethod
    def open(cls, filename, mode='r'):
        return cls._fs.open(filename, mode, collection=cls._collection)

    @classmethod
    def remove(cls, filename_or_spec):
        return cls._fs.remove(filename_or_spec, collection=cls._collection)

    @classmethod
    def list(cls):
        return cls._fs.list(collection=cls._collection)

    @classmethod
    def find(cls, spec):
        '''Find file metadata based on a file spec search'''
        return cls._coll.find(spec)
