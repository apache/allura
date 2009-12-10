from time import sleep

from pylons import c
from pymongo.errors import OperationFailure

from ming import Field, schema
from pyforge.model import VersionedArtifact, Snapshot, Message

class MyArtifactHistory(Snapshot):
    class __mongometa__:
        name='my_artifact_history'
    type_s='MyArtifact Snapshot'

    def original(self):
        return MyArtifact.m.get(_id=self.artifact_id)

    def shorthand_id(self):
        return '%s#%s' % (self.original().shorthand_id(), self.version)

    def url(self):
        return self.original().url() + '?version=%d' % self.version

    def index(self):
        result = Snapshot.index(self)
        result.update(
            title_s='Version %d of %s' % (
                self.version, self.original().shorthand_id()),
            type_s=self.type_s,
            text=self.data.text)
        return result

class MyArtifact(VersionedArtifact):
    class __mongometa__:
        name='my_artifact'
        history_class = MyArtifactHistory
    type_s = 'MyArtifact'

    text = Field(str, if_missing='')

    def url(self):
        return c.app.script_name + '/' + self._id.url_encode() + '/'

    def shorthand_id(self):
        return '%s/%s' % (self.type_s, self._id.url_encode())

    def index(self):
        result = VersionedArtifact.index(self)
        result.update(type_s=self.type_s, text=self.text)
        return result

    def root_comments(self):
        return MyArtifactComment.m.find(dict(artifact_id=self._id, parent_id=None))
    def reply(self):
        while True:
            try:
                c = MyArtifactComment.make(dict(artifact_id=self._id))
                c.m.insert()
                return c
            except OperationFailure:
                sleep(0.1)
                continue

class MyArtifactComment(Message):
    class __mongometa__:
        name='my_artifact_comment'
    type_s = 'MyArtifact Comment'

    artifact_id=Field(schema.ObjectId)

    def index(self):
        result = Message.index(self)
        author = self.author()
        result.update(
            title_s='Comment on %s by %s' % (
                self.artifact.shorthand_id(), author.display_name),
            type_s=self.type_s)
        return result

    @property
    def artifact(self):
        return MyArtifact.m.get(_id=self.artifact_id)

    def url(self):
        return self.artifact.url() + '#comment-' + self._id

    def shorthand_id(self):
        return '%s-%s' % (self.artifact.shorthand_id, self._id)
