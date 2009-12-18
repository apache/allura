from ming.datastore import DataStore
from ming import Session
from ming import Document, Field, schema
from datetime import datetime


class Issue0(Document):

    class __mongometa__:
        session = Session.by_name('main')
        name = 'issue'

    _id             = Field(schema.ObjectId)
    version         = Field(0)
    created_date    = Field(datetime, if_missing=datetime.utcnow)

    parent          = Field(schema.ObjectId, if_missing=None)
    summary         = Field(str)
    description     = Field(str, if_missing='')
    reported_by     = Field(str)
    assigned_to     = Field(str, if_missing='')
    milestone       = Field(str, if_missing='')
    status          = Field(str, if_missing='open')

Issue = Issue0



class Comment0(Document):

    class __mongometa__:
        session = Session.by_name('main')
        name = 'issue_comment'

    _id             = Field(schema.ObjectId)
    version         = Field(0)
    created_date    = Field(datetime, if_missing=datetime.utcnow)

    issue           = Field(schema.ObjectId)
    kind            = Field(str, if_missing='comment')
    reply_to        = Field(schema.ObjectId, if_missing=None)
    text            = Field(str)

Comment = Comment0



class Attachment0(Document):

    class __mongometa__:
        session = Session.by_name('main')
        name = 'issue_attachment'

    _id             = Field(schema.ObjectId)
    version         = Field(0)
    created_date    = Field(datetime, if_missing=datetime.utcnow)

    issue           = Field(schema.ObjectId)
    file_type       = Field(str)
    file_name       = Field(str)
    data            = Field(str)

Attachment = Attachment0
