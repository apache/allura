import time
from copy import deepcopy
from datetime import datetime, timedelta

from openid.store import nonce
from openid.association import Association

from ming import Document, Session, Field
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session

class OpenIdAssociation(MappedClass):
    class __mongometa__:
        name='oid_store_assoc'
        session = main_orm_session

    _id = FieldProperty(str) # server url
    assocs = FieldProperty([dict(
                key=str, value=str)])

    # Mimic openid.store.memstore.ServerAssocs
    def set_assoc(self, assoc):
        for a in self.assocs:
            if a['key'] == assoc.handle:
                a['value'] = assoc.serialize()
                return
        self.assocs.append(dict(key=assoc.handle, value=assoc.serialize()))

    def get_assoc(self, handle):
        for a in self.assocs:
            if a['key'] == handle:
                return Association.deserialize(a['value'])
        return None

    def remove_assoc(self, handle):
        old_len = len(self.assocs)
        self.assocs = [
            a for a in self.assocs
            if a['key'] != handle ]
        return old_len != len(self.assocs)

    def best_assoc(self):
        best = None
        for assoc in self.assocs:
            assoc = Association.deserialize(assoc['value'])
            if best is None or best.issued < assoc.issued:
                best = assoc
        if best:
            return best
        else:
            return None

    def cleanup_assocs(self):
        old_len = len(self.assocs)
        self.assocs = [ a for a in self.assocs
                        if Association.deserialize(a['value']).getExpiresIn() != 0 ]
        new_len = len(self.assocs)
        return (old_len - new_len), new_len

class OpenIdNonce(MappedClass):
    class __mongometa__:
        name='oid_store_nonce'
        session = main_orm_session

    _id = FieldProperty(str) # Nonce value
    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)
        
class OpenIdStore(object):

    def _get_assocs(self, server_url):
        assoc = OpenIdAssociation.query.get(_id=server_url)
        if assoc is None:
            assoc = OpenIdAssociation(_id=server_url)
        return assoc
    
    def storeAssociation(self, server_url, association):
        assocs = self._get_assocs(server_url)
        assocs.set_assoc(deepcopy(association))

    def getAssociation(self, server_url, handle=None):
        assocs = self._get_assocs(server_url)
        if handle is None:
            return assocs.best_assoc()
        else:
            return assocs.get_assoc(handle)

    def removeAssociation(self, server_url, handle):
        assocs = self._get_assocs(server_url)
        return assocs.remove_assoc(handle)

    def useNonce(self, server_url, timestamp, salt):
        if abs(timestamp - time.time()) > nonce.SKEW:
            return False
        key = str((server_url, timestamp, salt))
        if OpenIdNonce.query.get(_id=key) is None:
            OpenIdNonce(_id=key)
            return True
        else:
            return False

    def cleanupNonces(self):
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=nonce.SKEW)
        num_removed = OpenIdNonce.query.remove(dict(
                timestamp={'$lt': cutoff}))
        return num_removed

