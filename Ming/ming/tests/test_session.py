from collections import defaultdict
from unittest import TestCase, main

import mock
import pymongo

from ming.base import Object, Document, Field, Cursor
from ming import schema as S
from ming.session import Session

def mock_datastore():
    ds = mock.Mock()
    ds.db = defaultdict(mock_collection)
    return ds

def mock_collection():
    c = mock.Mock()
    c.find_one = mock.Mock(return_value={})
    return c

class TestSession(TestCase):

    def setUp(self):
        self.bind = mock_datastore()
        self.session = Session(self.bind)
        class TestDoc(Document):
            class __mongometa__:
                name='test_doc'
                session = self.session
                indexes = [ ('b','c') ]
            _id=Field(S.ObjectId, if_missing=None)
            a=Field(S.Int, if_missing=None)
            b=Field(S.Object, dict(a=S.Int(if_missing=None)))
        class TestDocNoSchema(Document):
            class __mongometa__:
                name='test_doc'
                session = self.session
        self.TestDoc = TestDoc
        self.TestDocNoSchema = TestDocNoSchema

    def test_base_session(self):
        impl = self.bind.db['test_doc']
        sess = self.session
        TestDoc = self.TestDoc
        self.assertEqual(sess.get(TestDoc, a=5), dict(a=None, b=dict(a=None), _id=None))
        sess.find(TestDoc, dict(a=5))
        sess.remove(TestDoc, dict(a=5))
        sess.group(TestDoc, 'a')
        sess.update_partial(TestDoc, dict(a=5), dict(b=6), False)
        
        impl.find_one.assert_called_with(dict(a=5))
        impl.find.assert_called_with(dict(a=5))
        impl.remove.assert_called_with(dict(a=5))
        impl.group.assert_called_with('a')
        impl.update.assert_called_with(dict(a=5), dict(b=6), False, safe=True)

        doc = TestDoc({})
        sess.save(doc)
        self.assertEqual(doc.a, None)
        self.assertEqual(doc.b, dict(a=None))
        del doc._id
        sess.insert(doc)
        sess.update(doc, dict(a=1))
        sess.delete(doc)
        impl.save.assert_called_with(doc, safe=True)
        impl.insert.assert_called_with(doc, safe=True)
        impl.update.assert_called_with(doc, dict(a=1), False, safe=True)
        impl.remove.assert_called_with(dict(_id=None))

        doc = self.TestDocNoSchema({'_id':5, 'a':5})
        sess.save(doc)
        impl.save.assert_called_with(dict(_id=5, a=5), safe=True)
        doc = self.TestDocNoSchema({'_id':5, 'a':5})
        sess.save(doc, 'a')
        impl.update.assert_called_with(dict(_id=5), {'$set':dict(a=5)})
        doc = self.TestDocNoSchema({'_id':5, 'a':5})
        impl.insert.return_value = pymongo.bson.ObjectId()
        sess.insert(doc)
        impl.insert.assert_called_with(dict(_id=5, a=5), safe=True)
        doc = self.TestDocNoSchema({'_id':5, 'a':5})
        sess.update(doc, dict(a=1))
        impl.update.assert_called_with(doc, dict(a=1), False, safe=True)

        sess.find_by(self.TestDoc, a=5)
        sess.count(self.TestDoc)
        sess.ensure_index(self.TestDoc, 'a')
        impl.find.assert_called_with(dict(a=5))
        impl.count.assert_called_with()
        impl.ensure_index.assert_called_with([ ('a', pymongo.ASCENDING) ])
        
        sess.ensure_indexes(self.TestDoc)
        impl.ensure_index.assert_called_with([
                ('b', pymongo.ASCENDING), ('c', pymongo.ASCENDING) ])

        doc = self.TestDocNoSchema(dict(_id=1, a=5))
        sess.set(doc, dict(b=5))
        self.assertEqual(doc.b, 5)

        doc = self.TestDocNoSchema(dict(_id=1, a=5))
        sess.increase_field(doc, a=60)
        impl.update.assert_called_with(dict(_id=1, a={'$lt': 60}),
                                       {'$set': dict(a=60)})
        sess.increase_field(doc, b=60)
        impl.update.assert_called_with(dict(_id=1, b={'$lt': 60}),
                                       {'$set': dict(b=60)})
        self.assertRaises(ValueError, sess.increase_field, doc, b=None)
        

        
        
        
        

        


if __name__ == '__main__':
    main()

