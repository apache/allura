from unittest import TestCase, main

import ming
from ming import Session, Field, Document
from ming import datastore as DS
from ming import schema as S

class TestDatastore(TestCase):

    def setUp(self):
        class TestDoc(Document):
            class __mongometa__:
                name='test_doc'
                session = Session.by_name('main')
            _id=Field(S.ObjectId, if_missing=None)
            a=Field(S.Int, if_missing=None)
            b=Field(S.Object, dict(a=S.Int(if_missing=None)))
        config = {
            'ming.main.master':'mongo://localhost:27017/test_db' }
        ming.configure(**config)
        self.session = TestDoc.__mongometa__.session

    def test_basic(self):
        self.assert_(repr(self.session.bind), 'DataStore(master=[{')
        self.session.bind.conn

    def test_master_slave(self):
        ms = DS.DataStore(master='mongo://localhost:23/test_db',
                          slave='mongo://localhost:27017/test_db')
        ms.conn # should failover to slave-only
        ms.db 
        ms_fail = DS.DataStore(master='mongo://localhost:23/test_db')
        self.assert_(ms_fail.conn is None)
        

if __name__ == '__main__':
    main()

