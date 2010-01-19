from time import sleep

from pylons import c
from pymongo.errors import OperationFailure

from ming import schema
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, ForeignIdProperty, RelationProperty
from datetime import datetime

from pyforge.model import Artifact, VersionedArtifact, Snapshot, Message, project_orm_session

class Globals(MappedClass):

    class __mongometa__:
        name = 'globals'
        session = project_orm_session

    type_s = 'Globals'
    _id = FieldProperty(schema.ObjectId)
    project_id = FieldProperty(str)
    last_issue_num = FieldProperty(int)
    status_names = FieldProperty(str)
    custom_fields = FieldProperty(str)

class IssueHistory(Snapshot):

    class __mongometa__:
        name = 'issue_history'

    def original(self):
        return Issue.query.get(_id=self.artifact_id)

    def shorthand_id(self):
        return '%s#%s' % (self.original().shorthand_id(), self.version)

    def url(self):
        return self.original().url() + '?version=%d' % self.version

    def index(self):
        result = Snapshot.index(self)
        result.update(
            title_s='Version %d of %s' % (
                self.version,self.original().title),
            type_s='Issue Snapshot',
            text=self.data.summary)
        return result

class Issue(VersionedArtifact):

    class __mongometa__:
        name = 'issue'
        history_class = IssueHistory

    type_s = 'Issue'
    _id = FieldProperty(schema.ObjectId)
    version = FieldProperty(0)
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)
    project_id = FieldProperty(str)

    parent_id = FieldProperty(schema.ObjectId, if_missing=None)
    issue_num = FieldProperty(int)
    summary = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    reported_by = FieldProperty(str)
    assigned_to = FieldProperty(str, if_missing='')
    milestone = FieldProperty(str, if_missing='')
    status = FieldProperty(str, if_missing='')
    custom_fields = FieldProperty({str:None})

    comments = RelationProperty('Comment')
    attachments = RelationProperty('Attachment')

    def url(self):
        return c.app.url + '/' + str(self.issue_num) + '/'

    def shorthand_id(self):
        return '%s/%s' % (self.type_s, self.issue_num)

    def index(self):
        result = VersionedArtifact.index(self)
        result.update(
            title_s='Issue %s' % self.issue_num,
            version_i=self.version,
            type_s=self.type_s,
            text=self.summary)
        return result

    def root_comments(self):
        if '_id' in self:
            return Comment.query.find(dict(issue_id=self._id, reply_to=None))
        else:
            return []

    def reply(self):
        while True:
            try:
                c = Comment(issue_id=self._id)
                return c
            except OperationFailure:
                sleep(0.1)
                continue

class Comment(Message):

    class __mongometa__:
        name = 'issue_comment'

    type_s = 'Issue Comment'
    _id = FieldProperty(schema.ObjectId)
    version = FieldProperty(0)
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)
    project_id = FieldProperty(str)

    author = FieldProperty(str, if_missing='')
    issue_id = ForeignIdProperty(Issue)
    kind = FieldProperty(str, if_missing='comment')
    reply_to_id = FieldProperty(schema.ObjectId, if_missing=None)
    text = FieldProperty(str)

    issue = RelationProperty('Issue')

    def index(self):
        result = Message.index(self)
        author = self.author()
        result.update(
            title_s='Comment on %s by %s' % (
                self.issue.shorthand_id(),
                author.display_name
            ),
            type_s=self.type_s
        )
        return result

    def url(self):
        return self.issue.url() + '#comment-' + str(self._id)

    def shorthand_id(self):
        return '%s-%s' % (self.issue.shorthand_id, self._id)

class Attachment(Artifact):

    class __mongometa__:
        name = 'issue_attachment'

    type_s = 'Issue Attachment'
    _id = FieldProperty(schema.ObjectId)
    version = FieldProperty(0)
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)
    project_id = FieldProperty(str)

    issue_id = ForeignIdProperty(Issue)
    file_type = FieldProperty(str)
    file_name = FieldProperty(str)
    data = FieldProperty(str)

    issue = RelationProperty('Issue')

    def index(self):
        result = Message.index(self)
        author = self.author()
        result.update(
            title_s='Attachment on %s by %s' % (
                self.issue.shorthand_id(),
                author.display_name
            ),
            type_s=self.type_s
        )
        return result

    def url(self):
        return self.issue.url() + '#attachment-' + self._id

    def shorthand_id(self):
        return '%s-%s' % (self.issue.shorthand_id, self._id)


MappedClass.compile_all()
