from datetime import datetime
from hashlib import sha1

from pylons import c, g
from ming import Document, Session, Field
from ming import schema as S
from pymongo.bson import ObjectId
from pymongo.errors import OperationFailure

from .session import ProjectSession

def nonce(length=4):
    return sha1(ObjectId().binary).hexdigest()[:4]

class Artifact(Document):
    class __mongometa__:
        session = ProjectSession(Session.by_name('main'))
        name='artifact'

    # Artifact base schema
    _id = Field(S.ObjectId)
    project_id = Field(S.String, if_missing=lambda:c.project._id)
    plugin_verson = Field(
        S.Object,
        { str: str },
        if_missing=lambda:{c.app.config.name:c.app.__version__})
    acl = Field(
        S.Object,
        dict(
            read=[str],
            write=[str],
            delete=[str],
            comment=[str]),
        if_missing=dict(
            read=['*anonymous', '*authenticated'],
            write=['*authenticated'],
            delete=['*authenticated'],
            comment=['*anonymous', '*authenticated']))

    def has_access(self, access_type):
        roles = [ '*anonymous' ]
        # Add other roles based on the username and groups
        acl = set(self.acl[access_type])
        for r in roles:
            if r in acl: return True
        return False

class Message(Artifact):
    class __mongometa__:
        session = ProjectSession(Session.by_name('main'))
        name='message'

    _id=Field(str, if_missing=nonce)
    parent_id=Field(str)
    app_id=Field(S.ObjectId, if_missing=lambda:c.app.config._id)
    timestamp=Field(datetime, if_missing=datetime.utcnow)
    author_id=Field(S.ObjectId, if_missing=g.user._id)
    text=Field(str)

    def reply(self):
        import time
        while True:
            try:
                new_id = self._id + '/' + nonce()
                msg = self.make(dict(
                        self,
                        _id=new_id,
                        parent_id=self._id,
                        timestamp=datetime.utcnow(),
                        author_id=g.user._id))
                msg.m.insert()
                break
            except OperationFailure:
                time.sleep(0.1)
                continue

    def descendants(self):
        q = self.m.find(dict(_id={'$gt':self._id}))
        for msg in q:
            if msg._id.startswith(self._id):
                yield msg
            else:
                break

    def replies(self):
        depth = self._id.count('/')
        for msg in self.descendants():
            if msg._id.count('/') - depth == 1:
                yield msg
