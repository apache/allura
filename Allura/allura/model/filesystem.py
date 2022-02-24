#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import os
import re
from io import BytesIO
import logging
import typing

import PIL
from gridfs import GridFS

from ming import schema
from ming.orm import session, FieldProperty
from ming.orm.declarative import MappedClass

from .session import project_orm_session
from allura.lib import utils

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


log = logging.getLogger(__name__)

SUPPORTED_BY_PIL = {
    'image/jpg',
    'image/jpeg',
    'image/pjpeg',
    'image/png',
    'image/x-png',
    'image/gif',
    'image/bmp'}


class File(MappedClass):

    class __mongometa__:
        session = project_orm_session
        name = 'fs'
        indexes = ['filename']

    query: 'Query[File]'

    _id = FieldProperty(schema.ObjectId)
    file_id = FieldProperty(schema.ObjectId)
    filename = FieldProperty(str, if_missing='unknown')
    content_type = FieldProperty(str)

    def __init__(self, **kw):
        super().__init__(**kw)
        if self.content_type is None:
            self.content_type = utils.guess_mime_type(self.filename)

    @classmethod
    def _fs(cls):
        gridfs_args = (session(cls).impl.db, cls._root_collection())
        try:
            # for some pymongo 2.x versions the _connect option is available to avoid index creation on every usage
            # (it'll still create indexes on delete & write)
            gridfs = GridFS(*gridfs_args, _connect=False)
        except TypeError:  # (unexpected keyword argument)
            # pymongo 3.0 removes the _connect arg
            # pymongo 3.1 makes index creation only happen on the very first write
            gridfs = GridFS(*gridfs_args)
        return gridfs

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
                if not s:
                    break
                fp_w.write(s)
        return obj

    @classmethod
    def from_path(cls, path, **kw):
        filename = os.path.basename(path)
        with open(path, 'rb') as stream:
            return cls.from_stream(filename, stream, **kw)

    @classmethod
    def from_data(cls, filename, data, **kw):
        return cls.from_stream(filename, BytesIO(data), **kw)

    def delete(self):
        self._fs().delete(self.file_id)
        super().delete()

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
        gridfs_file = self.rfile()
        return utils.serve_file(gridfs_file, self.filename, self.content_type,
                                last_modified=self._id.generation_time,
                                size=gridfs_file.length,
                                embed=embed)

    @classmethod
    def save_thumbnail(cls, filename, image,
                       content_type,
                       thumbnail_size=None,
                       thumbnail_meta=None,
                       square=False):
        height = image.size[0]
        width = image.size[1]
        if square and height != width:
            sz = max(width, height)
            if image.mode == 'RGBA':
                new_image = PIL.Image.new('RGBA', (sz, sz))
            else:
                new_image = PIL.Image.new('RGB', (sz, sz), 'white')
            if height < width:
                # image is wider than tall, so center horizontally
                new_image.paste(image, ((width - height) // 2, 0))
            elif height > width:
                # image is taller than wide, so center vertically
                new_image.paste(image, (0, (height - width) // 2))
            image = new_image

        if thumbnail_size:
            image.thumbnail(thumbnail_size, PIL.Image.ANTIALIAS)

        thumbnail_meta = thumbnail_meta or {}
        thumbnail = cls(
            filename=filename, content_type=content_type, **thumbnail_meta)
        format = image.format or 'png'
        if format == 'BMP':  # use jpg format if bmp is provided
            format = 'PNG'
        with thumbnail.wfile() as fp_w:
            save_kwargs = {}
            if 'transparency' in image.info:
                save_kwargs['transparency'] = image.info['transparency']
            image.save(fp_w, format, optimize=True, **save_kwargs)

        return thumbnail

    @classmethod
    def save_image(cls, filename, fp,
                   content_type=None,
                   thumbnail_size=None,
                   thumbnail_meta=None,
                   square=False,
                   save_original=False,
                   original_meta=None,
                   convert_bmp=False):
        if content_type is None:
            content_type = utils.guess_mime_type(filename)
        if not content_type.lower() in SUPPORTED_BY_PIL:
            log.debug('Content type %s from file %s not supported',
                      content_type, filename)
            return None, None

        try:
            image = PIL.Image.open(fp)
        except OSError as e:
            log.error('Error opening image %s %s', filename, e, exc_info=True)
            return None, None

        format = image.format
        save_anim = False

        if format == 'BMP' and convert_bmp: # use jpg format if bitmap is provided
            format = 'PNG'
            content_type = 'image/png'
            filename = re.sub('.bmp$', '.png', filename, flags=re.IGNORECASE)

        if format == 'GIF':
            save_anim = True # save all frames if GIF is provided

        if save_original:
            original_meta = original_meta or {}
            original = cls(
                filename=filename, content_type=content_type, **original_meta)
            with original.wfile() as fp_w:
                try:
                    save_kwargs = {}
                    if 'transparency' in image.info:
                        save_kwargs['transparency'] = image.info['transparency']
                    image.save(fp_w, format, save_all=save_anim, optimize=True, **save_kwargs)
                except Exception as e:
                    session(original).expunge(original)
                    log.exception('Error saving image %s %s %s', filename, content_type, format)
                    return None, None
        else:
            original = None

        thumbnail = cls.save_thumbnail(
            filename, image, content_type, thumbnail_size, thumbnail_meta, square)

        return original, thumbnail

    def is_image(self):
        return (self.content_type
                and self.content_type.lower() in SUPPORTED_BY_PIL)

    @property
    def length(self):
        return self.rfile().length
