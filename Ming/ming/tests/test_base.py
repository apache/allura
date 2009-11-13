from datetime import datetime
from decimal import Decimal
from unittest import TestCase, main

import mock

from ming.base import Object, Document, Field, Cursor
from ming import schema as S
from pymongo.bson import ObjectId

class TestObject(TestCase):

    def test_get_set(self):
        d = dict(a=1, b=2)
        obj = Object(d, c=3)
        self.assertEqual(1, obj.a)
        self.assertEqual(1, obj['a'])
        self.assertEqual(3, obj.c)
        self.assertEqual(3, obj['c'])
        obj.d = 5
        self.assertEqual(5, obj['d'])
        self.assertEqual(5, obj.d)
        self.assertEqual(obj, dict(a=1, b=2, c=3, d=5))
        self.assertRaises(AttributeError, getattr, obj, 'e')

    def test_from_bson(self):
        bson = dict(
            a=[1,2,3],
            b=dict(c=5))
        obj = Object.from_bson(bson)
        self.assertEqual(obj, dict(a=[1,2,3], b=dict(c=5)))

    def test_safe(self):
        now = datetime.now()
        oid = ObjectId()
        safe_obj = Object(
            a=[1,2,3],
            b=dict(a=12),
            c=[ 'foo', 1, 1L, 1.0, now, 
                Decimal('0.3'), None, oid ])
        safe_obj.make_safe()
        self.assertEqual(safe_obj, dict(
                a=[1,2,3], b=dict(a=12),
                c=[ 'foo', 1, 1L, 1.0, now,
                    0.3, None, oid ]))

        unsafe_obj = Object(
            my_tuple=(1,2,3))
        self.assertRaises(AssertionError, unsafe_obj.make_safe)

class TestDocument(TestCase):

    def setUp(self):
        self.MockSession = mock.Mock()
        class TestDoc(Document):
            class __mongometa__:
                name='test_doc'
                session = self.MockSession
            a=Field(S.Int, if_missing=None)
            b=Field(S.Object, dict(a=S.Int(if_missing=None)))
        self.TestDoc = TestDoc

    def test_field(self):
        doc = self.TestDoc(dict(a=1, b=dict(a=5)))
        self.assertEqual(doc.a, 1)
        self.assertEqual(doc.b, dict(a=5))
        doc.a = 5
        self.assertEqual(doc, dict(a=5, b=dict(a=5)))
        del doc.a
        self.assertEqual(doc, dict(b=dict(a=5)))
        self.assertRaises(AttributeError, getattr, doc, 'c')
        self.assertRaises(AttributeError, getattr, doc, 'a')

    def test_manager(self):
        other_session = mock.Mock()
        self.assertEqual(self.TestDoc.m(other_session).session, other_session)
        self.TestDoc.m.get(a=5)
        self.TestDoc.m.find(dict(a=5))
        self.TestDoc.m.remove(dict(a=5))
        self.TestDoc.m.find_by(a=5)
        self.TestDoc.m.count()
        self.TestDoc.m.ensure_index('foo')
        self.TestDoc.m.ensure_indexes()
        self.TestDoc.m.group(dict(a=5))
        self.TestDoc.m.update_partial(dict(a=5), dict(b=6))
        doc = self.TestDoc.make(dict(a=5))
        doc.m.save()
        doc.m.update(dict(b=10))
        doc.m.delete()
        doc.m.set(dict(b=10))
        doc.m.increase_field(a=10)
        self.MockSession.get.assert_called_with(self.TestDoc, a=5)
        self.MockSession.find.assert_called_with(self.TestDoc, dict(a=5))
        self.MockSession.remove.assert_called_with(self.TestDoc, dict(a=5))
        self.MockSession.find_by.assert_called_with(self.TestDoc, a=5)
        self.MockSession.count.assert_called_with(self.TestDoc)
        self.MockSession.ensure_index.assert_called_with(self.TestDoc, 'foo')
        self.MockSession.ensure_indexes.assert_called_with(self.TestDoc)
        self.MockSession.group.assert_called_with(self.TestDoc, dict(a=5))
        self.MockSession.update_partial.assert_called_with(
            self.TestDoc, dict(a=5), dict(b=6), False)
        self.MockSession.save.assert_called_with(doc)
        self.MockSession.update.assert_called_with(doc, dict(b=10), False)
        self.MockSession.delete.assert_called_with(doc)
        self.MockSession.set.assert_called_with(doc, dict(b=10))
        self.MockSession.increase_field.assert_called_with(doc, a=10)

    def test_migrate(self):
        doc = self.TestDoc.make(dict(a=5))
        self.MockSession.find = mock.Mock(return_value=[doc])
        self.TestDoc.m.migrate()
        self.MockSession.find.assert_called_with(self.TestDoc, {})
        self.MockSession.save.assert_called_with(doc)

class TestCursor(TestCase):

    def setUp(self):
        self.MockSession = mock.Mock()
        class TestDoc(Document):
            class __mongometa__:
                name='test_doc'
                session = self.MockSession
            a=Field(int)
            b=Field(S.Object, dict(a=int))
        self.TestDoc = TestDoc
        base_iter = iter([ {}, {}, {} ])
        mongo_cursor = mock.Mock()
        mongo_cursor.count = mock.Mock(return_value=3)
        mongo_cursor.__iter__ = base_iter
        mongo_cursor.next = base_iter.next
        mongo_cursor.limit = mock.Mock(return_value=mongo_cursor)
        mongo_cursor.hint = mock.Mock(return_value=mongo_cursor)
        mongo_cursor.skip = mock.Mock(return_value=mongo_cursor)
        mongo_cursor.sort = mock.Mock(return_value=mongo_cursor)
        self.cursor = Cursor(TestDoc, mongo_cursor)

    def test_cursor(self):
        obj = dict(a=None, b=dict(a=None))
        self.assertEqual(len(self.cursor), 3)
        self.assertEqual(self.cursor.count(), 3)
        self.assertEqual(self.cursor.next(), obj)
        self.cursor.limit(100)
        self.cursor.skip(10)
        self.cursor.hint('foo')
        self.cursor.sort('a')
        self.assertEqual(self.cursor.all(), [obj,obj])
        self.cursor.cursor.limit.assert_called_with(100)
        self.cursor.cursor.skip.assert_called_with(10)
        self.cursor.cursor.hint.assert_called_with('foo')
        self.cursor.cursor.sort.assert_called_with('a')

    def test_first(self):
        obj = dict(a=None, b=dict(a=None))
        self.assertEqual(self.cursor.first(), obj)
        self.assertEqual(self.cursor.first(), obj)
        self.assertEqual(self.cursor.first(), obj)
        self.assertEqual(self.cursor.first(), None)
                                 
    def test_one_full(self):
        self.assertRaises(ValueError, self.cursor.one)
                                 
    def test_one_empty(self):
        self.cursor.all()
        self.assertRaises(ValueError, self.cursor.one)
                                 
    def test_one_ok(self):
        self.cursor.next()
        self.cursor.next()
        obj = dict(a=None, b=dict(a=None))
        self.assertEqual(self.cursor.one(), obj)

if __name__ == '__main__':
    main()

