from datetime import datetime

import pymongo
from gridfs import GridFS

from .session import project_doc_session

from ming.base import build_mongometa
from ming import schema
from ming.orm.base import session
from ming.orm.property import FieldProperty, ForeignIdProperty, RelationProperty
from ming.orm.mapped_class import MappedClass, MappedClassMeta

from .session import project_orm_session

class File(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name = 'fs.files' # must always end in '.files'
        indexes = [
            'metadata.filename' ] # actual "stored" filename

    _id=FieldProperty(schema.ObjectId)
    # We don't actually store the filename here, just a randomish hash
    filename=FieldProperty(str, if_missing=lambda:str(pymongo.bson.ObjectId()))
    contentType=FieldProperty(str)
    length=FieldProperty(int)
    chunkSize=FieldProperty(int)
    uploadDate=FieldProperty(datetime)
    aliases=FieldProperty([str])
    metadata=FieldProperty(dict(
            # the real filename is stored here
            filename=str))
    md5=FieldProperty(str)
    next=FieldProperty(None)

    @classmethod
    def _fs(cls):
        return GridFS(session(cls).impl.db)

    @classmethod
    def _grid_coll_name(cls):
         # drop the '.files' suffix
        return cls.__mongometa__.name.rsplit('.', 1)[0]

    @classmethod
    def remove(cls, spec):
        return cls._fs().remove(spec, collection=cls._grid_coll_name())

    @classmethod
    def list(cls):
        return cls._fs().list(collection=cls._grid_coll_name())

    @classmethod
    def save(cls, filename, content_type, content, **metadata):
        f = cls.by_metadata(filename=filename).first()
        if f is None:
            fn = str(pymongo.bson.ObjectId())
        else:
            fn = f.filename
        with cls._fs().open(fn, 'w', collection=cls._grid_coll_name()) as fp:
            fp.content_type = content_type
            fp.metadata = dict(metadata, filename=filename)
            fp.write(content)
        return cls.query.get(filename=fn)

    @classmethod
    def by_metadata(cls, **kw):
        return cls.query.find(dict(
                ('metadata.%s' % k, v)
                for k,v in kw.iteritems()))

    @classmethod
    def create(cls, content_type=None, **meta_kwargs):
        fn = str(pymongo.bson.ObjectId())
        fp = cls._fs().open(fn, 'w', collection=cls._grid_coll_name())
        fp.content_type = content_type
        fp.metadata = dict(meta_kwargs)
        return fp

    def open(self, mode='r'):
        return self._fs().open(self.filename, mode, collection=self._grid_coll_name())

    def delete(self):
        self.remove(self.filename)
