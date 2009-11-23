from time import sleep
from datetime import datetime
from hashlib import sha1

from pylons import c
from ming import Document, Session, Field
from ming import schema as S
from pymongo.bson import ObjectId
from pymongo.errors import OperationFailure

from .session import ProjectSession

from pyforge.lib import search

def nonce(length=4):
    return sha1(ObjectId().binary).hexdigest()[:4]

class ArtifactSession(ProjectSession):

    def remove(self, cls, *args, **kwargs):
        for a in self.find(cls, *args, **kwargs):
            search.remove_artifact(a)
        ProjectSession.remove(self, cls, *args, **kwargs)

    def update_partial(self, cls, spec, fields, upsert):
        ProjectSession.update_partial(self, cls, spec, fields, upsert)
        for a in self.find(cls, spec):
            search.add_artifact(a)

    def save(self, doc, *args):
        ProjectSession.save(self, doc, *args)
        search.add_artifact(doc)

    def insert(self, doc):
        ProjectSession.insert(self, doc)
        search.add_artifact(doc)

    def update(self, doc, spec, upsert=False):
        ProjectSession.update(self, doc, spec, upsert)
        search.add_artifact(doc)

    def delete(self, doc):
        ProjectSession.delete(self, doc)
        search.remove_artifact(doc)

    def set(self, doc, fields_values):
        ProjectSession.set(self, doc, fields_values)
        search.add_artifact(doc)

    def increase_field(self, doc, **kwargs):
        ProjectSession.increase_field(self, doc, **kwargs)
        search.add_artifact(doc)

class Artifact(Document):
    class __mongometa__:
        session = ArtifactSession(Session.by_name('main'))
        name='artifact'

    # Artifact base schema
    _id = Field(S.ObjectId)
    project_id = Field(S.String, if_missing=lambda:c.project._id)
    plugin_verson = Field(
        S.Object,
        { str: str },
        if_missing=lambda:{c.app.config.name:c.app.__version__})
    acl = Field({str:[str]})

    def index(self):
        from .project import Project
        project = Project.m.get(_id=self.project_id)
        if hasattr(self._id, 'url_encode'):
            _id = self._id.url_encode()
        id = '%s.%s#%s' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self._id)
        return dict(
            id=id,
            title_s='Artifact %s' % self._id,
            project_id_s=self.project_id,
            project_name_t=project.name,
            project_shortname_t=project.shortname,
            url_s=self.url(),
            type_s='Generic Artifact')

    def url(self):
        raise NotImplementedError, 'url'

class Message(Artifact):
    class __mongometa__:
        session = ArtifactSession(Session.by_name('main'))
        name='message'

    _id=Field(str, if_missing=nonce)
    parent_id=Field(str)
    app_id=Field(S.ObjectId, if_missing=lambda:c.app.config._id)
    timestamp=Field(datetime, if_missing=datetime.utcnow)
    author_id=Field(S.ObjectId, if_missing=lambda:c.user._id)
    text=Field(str, if_missing='')

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

    def index(self):
        result = Artifact.index(self)
        author = self.author()
        result.update(
            author_user_name_t=author.username,
            author_display_name_t=author.display_name,
            timestamp_dt=self.timestamp,
            text=self.text,
            type_s='Generic Message')
        return result
