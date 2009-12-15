import time
from copy import deepcopy
from datetime import datetime, timedelta

from openid.store import nonce
from openid.association import Association

from ming import Document, Session, Field

class OpenIdAssociation(Document):
    class __mongometa__:
        name='oid_store'
        session = Session.by_name('main')

    _id = Field(str) # server url
    assocs = Field({str:str})

    # Mimic openid.store.memstore.ServerAssocs
    def set_assoc(self, assoc):
        self.assocs[assoc.handle] = assoc.serialize()
        self.m.save()

    def get_assoc(self, handle):
        return Association.deserialize(self.assocs.get(handle))

    def remove_assoc(self, handle):
        try:
            del self.assocs[handle]
            self.m.save()
        except KeyError:
            return False
        else:
            return True

    def best_assoc(self):
        best = None
        for assoc in self.assocs.itervalues():
            assoc = Association.deserialize(assoc)
            if best is None or best.issued < assoc.issued:
                best = assoc
        if best:
            return best
        else:
            return None

    def cleanup_assocs(self):
        old_len = len(self.assocs)
        self.assocs = dict(
            (handle, assoc) for handle, assoc in self.assocs.iteritems()
            if assoc.getExpiresIn() != 0)
        new_len = len(self.assocs)
        return (old_len - new_len), new_len

class OpenIdNonce(Document):
    class __mongometa__:
        name='oid_store'
        session = Session.by_name('main')

    _id = Field(str) # Nonce value
    timestamp = Field(datetime, if_missing=datetime.utcnow)
        
class OpenIdStore(object):

    def _get_assocs(self, server_url):
        assoc = OpenIdAssociation.m.get(_id=server_url)
        if assoc is None:
            assoc = OpenIdAssociation.make(dict(_id=server_url))
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
        if OpenIdNonce.m.get(_id=key) is None:
            OpenIdNonce.make(dict(_id=key)).m.save()
            return True
        else:
            return False

    def cleanupNonces(self):
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=nonce.SKEW)
        num_removed = OpenIdNonce.m.remove(dict(
                timestamp={'$lt': cutoff}))
        return num_removed

