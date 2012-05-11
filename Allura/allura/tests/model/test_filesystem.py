# -*- coding: utf-8 -*-
import os
from unittest import TestCase
from cStringIO import StringIO

from pylons import response
from ming.orm import session, Mapper


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

    def test_serve(self):
        f = File.from_data(u'te s\u0b6e1.txt', 'test1')
        self.session.flush()
        assert [ 'test1' ] == list(f.serve())
        assert response.content_type == f.content_type
        assert 'Content-Disposition' not in response.headers
        assert [ 'test1' ] == list(f.serve(False))
        assert response.content_type == f.content_type
        assert response.headers['Content-Disposition'] == \
            'attachment;filename="te s\xe0\xad\xae1.txt"'

    def test_image(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', 'data', 'user.png')
        with open(path) as fp:
            f, t = File.save_image(
                'user.png',
                fp,
                thumbnail_size=(16,16),
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

    def _assert_content(self, f, content):
        result = f.rfile().read()
        assert result == content, result
