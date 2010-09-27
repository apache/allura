from mimetypes import guess_type
from datetime import datetime

import Image
import pymongo
from gridfs import GridFS
import tg

from .session import project_doc_session

from ming.base import build_mongometa
from ming import schema
from ming.orm.base import session
from ming.orm.property import FieldProperty, ForeignIdProperty, RelationProperty
from ming.orm.mapped_class import MappedClass, MappedClassMeta

from .session import project_orm_session

SUPPORTED_BY_PIL=set([
        'image/jpg',
        'image/png',
        'image/jpeg',
        'image/gif'])

class File(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name = 'fs.files' # must always end in '.files'
        indexes = [
            'metadata.filename' ] # actual "stored" filename

    _id=FieldProperty(schema.ObjectId)
    # We don't actually store the filename here, just a randomish hash
    filename=FieldProperty(str, if_missing=lambda:str(pymongo.bson.ObjectId()))
    # There is much weirdness in gridfs; the fp.content_type property is stored
    # in the contentType field
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
        fp.metadata =dict(meta_kwargs)
        return fp

    @classmethod
    def save_image(cls, filename, fp,
                   content_type=None,
                   thumbnail_size=None,
                   thumbnail_meta=None,
                   square=False,
                   save_original=False,
                   original_meta=None):
        if content_type is None:
            content_type = guess_type(filename)
            if content_type[0]: content_type = content_type[0]
            else: content_type = 'application/octet-stream'
        if not content_type.lower() in SUPPORTED_BY_PIL:
            return None, None
        thumbnail_meta = thumbnail_meta or {}
        image = Image.open(fp)
        format = image.format
        if save_original:
            original_meta = original_meta or {}
            with cls.create(content_type=content_type,
                            filename=filename,
                            **original_meta) as fp_w:
                filename = fp_w.name
                if 'transparency' in image.info:
                    image.save(fp_w, format, transparency=image.info['transparency'])
                else:
                    image.save(fp_w, format)
            original = cls.query.get(filename=fp_w.name)
        else:
            original=None
        if square:
            height = image.size[0]
            width = image.size[1]
            sz = max(width, height)
            if 'transparency' in image.info:
                new_image = Image.new('RGBA', (sz,sz))
            else:
                new_image = Image.new('RGB', (sz,sz), 'white')
            if height < width:
                # image is wider than tall, so center horizontally
                new_image.paste(image, ((width-height)/2, 0))
            elif height > width:
                # image is taller than wide, so center vertically
                new_image.paste(image, (0, (height-width)/2))
            image = new_image
        if thumbnail_size:
            image.thumbnail(thumbnail_size, Image.ANTIALIAS)
        with cls.create(content_type=content_type,
                        filename=filename,
                        **thumbnail_meta) as fp_w:
            if 'transparency' in image.info:
                image.save(fp_w, format, transparency=image.info['transparency'])
            else:
                image.save(fp_w, format)
        thumbnail=cls.query.get(filename=fp_w.name)
        return original, thumbnail
        
    def is_image(self):
        if not self.contentType:
            return False
        return self.contentType.lower() in SUPPORTED_BY_PIL

    def open(self, mode='r'):
        return self._fs().open(self.filename, mode, collection=self._grid_coll_name())

    def delete(self):
        self.remove(self.filename)

