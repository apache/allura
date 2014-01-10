# -*- coding: utf-8 -*-

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
from unittest import TestCase
from cStringIO import StringIO
from io import BytesIO

from pylons import tmpl_context as c
from ming.orm import session, Mapper
from nose.tools import assert_equal
from mock import patch
from webob import Request, Response

from allura import model as M
from alluratest.controller import setup_unit_test


class File(M.File):

    class __mongometa__:
        session = M.session.main_orm_session
Mapper.compile_all()


class TestFile(TestCase):

    def setUp(self):
        setup_unit_test()
        self.session = session(File)
        self.conn = M.session.main_doc_session.db._connection
        self.db = M.session.main_doc_session.db

        self.db.fs.remove()
        self.db.fs.files.remove()
        self.db.fs.chunks.remove()

    def test_from_stream(self):
        f = File.from_stream('test1.txt', StringIO('test1'))
        self.session.flush()
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 1
        assert self.db.fs.chunks.count() == 1
        assert f.filename == 'test1.txt'
        assert f.content_type == 'text/plain'
        self._assert_content(f, 'test1')

    def test_from_data(self):
        f = File.from_data('test2.txt', 'test2')
        self.session.flush(f)
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 1
        assert self.db.fs.chunks.count() == 1
        assert f.filename == 'test2.txt'
        assert f.content_type == 'text/plain'
        self._assert_content(f, 'test2')

    def test_from_path(self):
        path = __file__.rstrip('c')
        f = File.from_path(path)
        self.session.flush()
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 1
        assert self.db.fs.chunks.count() >= 1
        assert f.filename == os.path.basename(path)
        text = f.rfile().read()
        assert text.startswith('# -*-')

    def test_delete(self):
        f = File.from_data('test1.txt', 'test1')
        self.session.flush()
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 1
        assert self.db.fs.chunks.count() == 1
        f.delete()
        self.session.flush()
        assert self.db.fs.count() == 0
        assert self.db.fs.files.count() == 0
        assert self.db.fs.chunks.count() == 0

    def test_remove(self):
        File.from_data('test1.txt', 'test1')
        File.from_data('test2.txt', 'test2')
        self.session.flush()
        assert self.db.fs.count() == 2
        assert self.db.fs.files.count() == 2
        assert self.db.fs.chunks.count() == 2
        File.remove(dict(filename='test1.txt'))
        self.session.flush()
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 1
        assert self.db.fs.chunks.count() == 1

    def test_overwrite(self):
        f = File.from_data('test1.txt', 'test1')
        self.session.flush()
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 1
        assert self.db.fs.chunks.count() == 1
        self._assert_content(f, 'test1')
        with f.wfile() as fp:
            fp.write('test2')
        self.session.flush()
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 2
        assert self.db.fs.chunks.count() == 2
        self._assert_content(f, 'test2')

    def test_serve_embed(self):
        f = File.from_data(u'te s\u0b6e1.txt', 'test1')
        self.session.flush()
        with patch('allura.lib.utils.tg.request', Request.blank('/')), \
                patch('allura.lib.utils.pylons.response', Response()) as response, \
                patch('allura.lib.utils.etag_cache') as etag_cache:
            response_body = list(f.serve())
            etag_cache.assert_called_once_with(u'{}?{}'.format(f.filename,
                                                               f._id.generation_time).encode('utf-8'))
            assert_equal(['test1'], response_body)
            assert_equal(response.content_type, f.content_type)
            assert 'Content-Disposition' not in response.headers

    def test_serve_embed_false(self):
        f = File.from_data(u'te s\u0b6e1.txt', 'test1')
        self.session.flush()
        with patch('allura.lib.utils.tg.request', Request.blank('/')), \
                patch('allura.lib.utils.pylons.response', Response()) as response, \
                patch('allura.lib.utils.etag_cache') as etag_cache:
            response_body = list(f.serve(embed=False))
            etag_cache.assert_called_once_with(u'{}?{}'.format(f.filename,
                                                               f._id.generation_time).encode('utf-8'))
            assert_equal(['test1'], response_body)
            assert_equal(response.content_type, f.content_type)
            assert_equal(response.headers['Content-Disposition'],
                         'attachment;filename="te s\xe0\xad\xae1.txt"')

    def test_image(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', 'data', 'user.png')
        with open(path) as fp:
            f, t = File.save_image(
                'user.png',
                fp,
                thumbnail_size=(16, 16),
                square=True,
                save_original=True)
        self.session.flush()
        assert f.content_type == 'image/png'
        assert f.is_image()
        assert t.content_type == 'image/png'
        assert t.is_image()
        assert f.filename == t.filename
        assert self.db.fs.count() == 2
        assert self.db.fs.files.count() == 2
        assert self.db.fs.chunks.count() == 2

    def test_not_image(self):
        f, t = File.save_image(
            'file.txt',
            StringIO('blah'),
            thumbnail_size=(16, 16),
            square=True,
            save_original=True)
        assert f == None
        assert t == None

    def test_invalid_image(self):
        f, t = File.save_image(
            'bogus.png',
            StringIO('bogus data here!'),
            thumbnail_size=(16, 16),
            square=True,
            save_original=True)
        assert f == None
        assert t == None

    def test_partial_image_as_attachment(self):
        path = os.path.join(os.path.dirname(__file__),
                            '..', 'data', 'user.png')
        fp = BytesIO(open(path, 'rb').read(500))
        c.app.config._id = None
        attachment = M.BaseAttachment.save_attachment('user.png', fp,
                                                      save_original=True)
        assert type(attachment) != tuple   # tuple is for (img, thumb) pairs
        assert_equal(attachment.length, 500)
        assert_equal(attachment.filename, 'user.png')

    def test_attachment_name_encoding(self):
        path = os.path.join(os.path.dirname(__file__),
                            '..', 'data', 'user.png')
        fp = open(path, 'rb')
        c.app.config._id = None
        attachment = M.BaseAttachment.save_attachment(
            b'Strukturpr\xfcfung.dvi', fp,
            save_original=True)
        assert type(attachment) != tuple   # tuple is for (img, thumb) pairs
        assert_equal(attachment.filename, u'Strukturpr\xfcfung.dvi')

    def _assert_content(self, f, content):
        result = f.rfile().read()
        assert result == content, result
