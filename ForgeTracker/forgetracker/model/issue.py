from time import sleep

from pylons import c
from pymongo.errors import OperationFailure

from ming.datastore import DataStore
from ming import Document, Field, schema
from datetime import datetime

from pyforge.model import Message

class Globals(Document):

    class __mongometa__:
        name = 'globals'

    type_s          = 'Globals'
    _id             = Field(schema.ObjectId)
    project_id      = Field(schema.ObjectId)
    last_issue_num  = Field(int)


class Issue0(Document):

    class __mongometa__:
        name = 'issue'

    type_s          = 'Issue'
    _id             = Field(schema.ObjectId)
    version         = Field(0)
    created_date    = Field(datetime, if_missing=datetime.utcnow)
    project_id      = Field(schema.ObjectId)

    parent_id       = Field(schema.ObjectId, if_missing=None)
    issue_num       = Field(int)
    summary         = Field(str)
    description     = Field(str, if_missing='')
    reported_by     = Field(str)
    assigned_to     = Field(str, if_missing='')
    milestone       = Field(str, if_missing='')
    status          = Field(str, if_missing='open')

    def url(self):
        return c.app.script_name + '/' + self.issue_num + '/'

    def shorthand_id(self):
        return '%s/%s' % (self.type_s, self._id)

    def index(self):
        return self

    def root_comments(self):
        return Comment.m.find(dict(issue_id=self._id, reply_to=None))

    def attachments(self):
        return Attachment.m.find(dict(issue_id=self._id))

    def reply(self):
        while True:
            try:
                c = Comment.make(dict(issue_id=self._id))
                c.m.insert()
                return c
            except OperationFailure:
                sleep(0.1)
                continue

Issue = Issue0



class Comment0(Message):

    class __mongometa__:
        name = 'issue_comment'

    type_s          = 'Issue Comment'
    _id             = Field(schema.ObjectId)
    version         = Field(0)
    created_date    = Field(datetime, if_missing=datetime.utcnow)
    project_id      = Field(schema.ObjectId)

    issue_id        = Field(schema.ObjectId)
    kind            = Field(str, if_missing='comment')
    reply_to_id     = Field(schema.ObjectId, if_missing=None)
    text            = Field(str)

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

    @property
    def issue(self):
        return Issue.m.get(_id=self.issue_id)

    def url(self):
        return self.issue.url() + '#comment-' + self._id

    def shorthand_id(self):
        return '%s-%s' % (self.issue.shorthand_id, self._id)

Comment = Comment0



class Attachment0(Message):

    class __mongometa__:
        name = 'issue_attachment'

    type_s          = 'Issue Attachment'
    _id             = Field(schema.ObjectId)
    version         = Field(0)
    created_date    = Field(datetime, if_missing=datetime.utcnow)
    project_id      = Field(schema.ObjectId)

    issue_id        = Field(schema.ObjectId)
    file_type       = Field(str)
    file_name       = Field(str)
    data            = Field(str)

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

    @property
    def issue(self):
        return Issue.m.get(_id=self.issue_id)

    def url(self):
        return self.issue.url() + '#attachment-' + self._id

    def shorthand_id(self):
        return '%s-%s' % (self.issue.shorthand_id, self._id)

Attachment = Attachment0
