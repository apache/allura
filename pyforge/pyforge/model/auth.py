from ming import Document, Session, Field
from ming import schema as S

class User(Document):
    class __mongometa__:
        name='user'
        session = Session.by_name('main')

    _id=Field(S.ObjectId)
    login=Field(str)
    display_name=Field(str)
    groups=Field([str], if_empty=['*anonymous', '*authenticated' ])

    def roles(self):
        yield self.login
        for g in self.groups:
            yield g
