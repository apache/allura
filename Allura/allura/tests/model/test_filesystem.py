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
from io import BytesIO

import ming
from tg import tmpl_context as c
from ming.orm import session, Mapper
from mock import patch
from webob import Request, Response

from allura import model as M
from alluratest.controller import setup_unit_test


class File(M.File):

    class __mongometa__:
        session = M.session.main_orm_session
Mapper.compile_all()


class TestFile(TestCase):

    def setup_method(self, method):
        config = {
            'ming.main.uri': 'mim://host/allura',
            'ming.project.uri': 'mim://host/project-data',
        }
        ming.configure(**config)
        setup_unit_test()
        self.session = session(File)
        self.conn = M.session.main_doc_session.db._connection
        self.db = M.session.main_doc_session.db

        self.db.fs.remove()
        self.db.fs.files.remove()
        self.db.fs.chunks.remove()

    def test_from_stream(self):
        f = File.from_stream('test1.txt', BytesIO(b'test1'))
        self.session.flush()
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 1
        assert self.db.fs.chunks.count() == 1
        assert f.filename == 'test1.txt'
        assert f.content_type == 'text/plain'
        self._assert_content(f, b'test1')

    def test_from_data(self):
        f = File.from_data('test2.txt', b'test2')
        self.session.flush(f)
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 1
        assert self.db.fs.chunks.count() == 1
        assert f.filename == 'test2.txt'
        assert f.content_type == 'text/plain'
        self._assert_content(f, b'test2')

    def test_from_path(self):
        path = __file__.rstrip('c')
        f = File.from_path(path)
        self.session.flush()
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 1
        assert self.db.fs.chunks.count() >= 1
        assert f.filename == os.path.basename(path)
        text = f.rfile().read()

    def test_delete(self):
        f = File.from_data('test1.txt', b'test1')
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
        File.from_data('test1.txt', b'test1')
        File.from_data('test2.txt', b'test2')
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
        f = File.from_data('test1.txt', b'test1')
        self.session.flush()
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 1
        assert self.db.fs.chunks.count() == 1
        self._assert_content(f, b'test1')
        with f.wfile() as fp:
            fp.write(b'test2')
        self.session.flush()
        assert self.db.fs.count() == 1
        assert self.db.fs.files.count() == 2
        assert self.db.fs.chunks.count() == 2
        self._assert_content(f, b'test2')

    def test_serve_embed(self):
        f = File.from_data('te s\u0b6e1.txt', b'test1')
        self.session.flush()
        with patch('allura.lib.utils.tg.request', Request.blank('/')), \
                patch('allura.lib.utils.tg.response', Response()) as response, \
                patch('allura.lib.utils.etag_cache') as etag_cache:
            response_body = list(f.serve())
            etag_cache.assert_called_once_with('{}?{}'.format(f.filename,
                                                               f._id.generation_time).encode('utf-8'))
            assert [b'test1'] == response_body
            assert response.content_type == f.content_type
            assert 'Content-Disposition' not in response.headers

    def test_serve_embed_false(self):
        f = File.from_data('te s\u0b6e1.txt', b'test1')
        self.session.flush()
        with patch('allura.lib.utils.tg.request', Request.blank('/')), \
                patch('allura.lib.utils.tg.response', Response()) as response, \
                patch('allura.lib.utils.etag_cache') as etag_cache:
            response_body = list(f.serve(embed=False))
            etag_cache.assert_called_once_with('{}?{}'.format(f.filename,
                                                               f._id.generation_time).encode('utf-8'))
            assert [b'test1'] == response_body
            assert response.content_type == f.content_type
            assert (response.headers['Content-Disposition'] ==
                         'attachment;filename="te%20s%E0%AD%AE1.txt"')

    def test_image(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', 'data', 'user.png')
        with open(path, 'rb') as fp:
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
            BytesIO(b'blah'),
            thumbnail_size=(16, 16),
            square=True,
            save_original=True)
        assert f is None
        assert t is None

    def test_invalid_image(self):
        f, t = File.save_image(
            'bogus.png',
            BytesIO(b'bogus data here!'),
            thumbnail_size=(16, 16),
            square=True,
            save_original=True)
        assert f is None
        assert t is None

    def test_partial_image_as_attachment(self):
        path = os.path.join(os.path.dirname(__file__),
                            '..', 'data', 'user.png')
        fp = BytesIO(open(path, 'rb').read(500))
        c.app.config._id = None
        attachment = M.BaseAttachment.save_attachment('user.png', fp,
                                                      save_original=True)
        assert not isinstance(attachment, tuple)   # tuple is for (img, thumb) pairs
        assert attachment.length == 500
        assert attachment.filename == 'user.png'

    def test_attachment_name_encoding(self):
        path = os.path.join(os.path.dirname(__file__),
                            '..', 'data', 'user.png')
        fp = open(path, 'rb')
        c.app.config._id = None
        attachment = M.BaseAttachment.save_attachment(
            'Strukturpr\xfcfung.dvi', fp,
            save_original=True)
        assert not isinstance(attachment, tuple)   # tuple is for (img, thumb) pairs
        assert attachment.filename == 'Strukturpr\xfcfung.dvi'

    def _assert_content(self, f, content):
        result = f.rfile().read()
        assert result == content, result
