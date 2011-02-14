import os
from cStringIO import StringIO

import pylons
import Image
from gridfs import GridFS

from ming import schema
from ming.orm.base import session
from ming.orm.property import FieldProperty
from ming.orm.mapped_class import MappedClass

from .session import project_orm_session
from allura.lib import utils


SUPPORTED_BY_PIL=set([
        'image/jpg',
        'image/jpeg',
        'image/png',
        'image/gif'])

class File(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name = 'fs'
        indexes = [ 'filename' ]

    _id = FieldProperty(schema.ObjectId)
    file_id = FieldProperty(schema.ObjectId)
    filename=FieldProperty(str, if_missing='unknown')
    content_type=FieldProperty(str)

    def __init__(self, **kw):
        super(File, self).__init__(**kw)
        if self.content_type is None:
            self.content_type = utils.guess_mime_type(self.filename)

    @classmethod
    def _fs(cls):
        return GridFS(
            session(cls).impl.db,
            cls._root_collection())

    @classmethod
    def _root_collection(cls):
        return cls.__mongometa__.name

    @classmethod
    def remove(cls, spec):
        for fobj in cls.query.find(spec):
            fobj.delete()

    @classmethod
    def from_stream(cls, filename, stream, **kw):
        obj = cls(filename=filename, **kw)
        with obj.wfile() as fp_w:
            while True:
                s = stream.read()
                if not s: break
                fp_w.write(s)
        return obj

    @classmethod
    def from_path(cls, path, **kw):
        filename = os.path.basename(path)
        with open(path, 'rb') as stream:
            return cls.from_stream(filename, stream, **kw)

    @classmethod
    def from_data(cls, filename, data, **kw):
        return cls.from_stream(filename, StringIO(data), **kw)

    def delete(self):
        self._fs().delete(self.file_id)
        super(File, self).delete()

    def rfile(self):
        return self._fs().get(self.file_id)

    def wfile(self):
        fp = self._fs().new_file(
            filename=self.filename,
            content_type=self.content_type)
        self.file_id = fp._id
        return fp

    def serve(self, embed=True):
        '''Sets the response headers and serves as a wsgi iter'''
        fp = self.rfile()
        pylons.response.headers['Content-Type'] = ''
        pylons.response.content_type = fp.content_type.encode('utf-8')
        if not embed:
            pylons.response.headers.add(
                'Content-Disposition',
                'attachment;filename=%s' % self.filename)
        return iter(fp)

    @classmethod
    def save_thumbnail(cls, filename, image,
                   content_type,
                   thumbnail_size=None,
                   thumbnail_meta=None,
                   square=False):
        format = image.format
        height = image.size[0]
        width = image.size[1]
        if square and height != width:
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

        thumbnail_meta = thumbnail_meta or {}
        thumbnail = cls(
            filename=filename, content_type=content_type, **thumbnail_meta)
        with thumbnail.wfile() as fp_w:
            if 'transparency' in image.info:
                image.save(fp_w, format, transparency=image.info['transparency'])
            else:
                image.save(fp_w, format)

        return thumbnail

    @classmethod
    def save_image(cls, filename, fp,
                   content_type=None,
                   thumbnail_size=None,
                   thumbnail_meta=None,
                   square=False,
                   save_original=False,
                   original_meta=None):
        if content_type is None:
            content_type = utils.guess_mime_type(filename)
        if not content_type.lower() in SUPPORTED_BY_PIL:
            return None, None

        image = Image.open(fp)
        format = image.format
        if save_original:
            original_meta = original_meta or {}
            original = cls(
                filename=filename, content_type=content_type, **original_meta)
            with original.wfile() as fp_w:
                if 'transparency' in image.info:
                    image.save(fp_w, format, transparency=image.info['transparency'])
                else:
                    image.save(fp_w, format)
        else:
            original = None

        thumbnail = cls.save_thumbnail(filename, image, content_type, thumbnail_size, thumbnail_meta, square)

        return original, thumbnail

    def is_image(self):
        return (self.content_type
                and self.content_type.lower() in SUPPORTED_BY_PIL)
    
    @property
    def length(self):
        return self.rfile().length
