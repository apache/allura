from base64 import b64encode
from random import randint
from hashlib import sha256

from ming import Document, Session, Field
from ming import schema as S

from .session import ProjectSession

SALT_LENGTH=8

def encode_password(password, salt=None):
    if salt is None:
        salt = ''.join(chr(randint(1, 0x7f))
                       for i in xrange(SALT_LENGTH))
    hashpass = sha256(salt + password.encode('utf-8')).digest()
    return 'sha256' + salt + b64encode(hashpass)

class User(Document):
    SALT_LEN=8
    class __mongometa__:
        name='user'
        session = Session.by_name('main')

    _id=Field(S.ObjectId)
    username=Field(str)
    display_name=Field(str)
    open_ids=Field([str])
    password=Field(str)

    def set_password(self, password):
        self.password = encode_password(password)

    def validate_password(self, password):
        if not self.password: return False
        salt = str(self.password[6:6+self.SALT_LEN])
        check = encode_password(password, salt)
        return check == self.password

User.anonymous = User.make(dict(
        _id=None, username='*anonymous', display_name='Anonymous Coward'))

class ProjectRole(Document):
    class __mongometa__:
        session = ProjectSession(Session.by_name('main'))
        name='user'
    
    _id = Field(str)
    user_id = Field(S.ObjectId, if_missing=None) # if role is a user
    roles = Field([str])

    @property
    def user(self):
        return User.m.get(_id=self.user_id)

    def role_iter(self, visited=None):
        if visited is None: visited = set()
        if self._id not in visited: 
            yield self._id
            visited.add(self._id)
            for r in self.roles:
                for rr in ProjectRole.m.get(r).role_iter(visited):
                    yield rr
    
