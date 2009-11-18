from time import sleep
from datetime import datetime
from hashlib import sha1

from pylons import c
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
    acl = Field({str:[str]})

class Message(Artifact):
    class __mongometa__:
        session = ProjectSession(Session.by_name('main'))
        name='message'

    _id=Field(str, if_missing=nonce)
    parent_id=Field(str)
    app_id=Field(S.ObjectId, if_missing=lambda:c.app.config._id)
    timestamp=Field(datetime, if_missing=datetime.utcnow)
    author_id=Field(S.ObjectId, if_missing=lambda:c.user._id)
    text=Field(str)

    def author(self):
        from .auth import User
        return User.m.get(_id=self.author_id)

    def reply(self):
        while True:
            try:
                new_id = self._id + '/' + nonce()
                msg = self.make(dict(
                        self,
                        _id=new_id,
                        parent_id=self._id,
                        timestamp=datetime.utcnow(),
                        author_id=c.user._id))
                msg.m.insert()
                return msg
            except OperationFailure:
                sleep(0.1)
                continue # pragma: no cover

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
