from time import sleep
from datetime import datetime

from pylons import c
from pymongo.errors import OperationFailure
import pymongo

from ming import schema
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, ForeignIdProperty, RelationProperty
from datetime import datetime

from pyforge.model import Artifact, VersionedArtifact, Snapshot, Message, project_orm_session, Project
from pyforge.model import File, User, Feed
from pyforge.lib import helpers as h

class Globals(MappedClass):

    class __mongometa__:
        name = 'globals'
        session = project_orm_session

    type_s = 'Globals'
    _id = FieldProperty(schema.ObjectId)
    app_config_id = ForeignIdProperty('AppConfig', if_missing=lambda:c.app.config._id)
    last_ticket_num = FieldProperty(int)
    status_names = FieldProperty(str)
    custom_fields = FieldProperty(str)

class TicketHistory(Snapshot):

    class __mongometa__:
        name = 'ticket_history'

    def original(self):
        return Ticket.query.get(_id=self.artifact_id)

    def shorthand_id(self):
        return '%s#%s' % (self.original().shorthand_id(), self.version)

    def url(self):
        return self.original().url() + '?version=%d' % self.version

    def index(self):
        result = Snapshot.index(self)
        result.update(
            title_s='Version %d of %s' % (
                self.version,self.original().title),
            type_s='Ticket Snapshot',
            text=self.data.summary)
        return result

class Ticket(VersionedArtifact):
    class __mongometa__:
        name = 'ticket'
        history_class = TicketHistory

    type_s = 'Ticket'
    _id = FieldProperty(schema.ObjectId)
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)

    parent_id = FieldProperty(schema.ObjectId, if_missing=None)
    ticket_num = FieldProperty(int)
    summary = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    reported_by_id = FieldProperty(schema.ObjectId, if_missing=lambda:c.user._id)
    assigned_to_id = FieldProperty(schema.ObjectId, if_missing=None)
    milestone = FieldProperty(str, if_missing='')
    status = FieldProperty(str, if_missing='')
    custom_fields = FieldProperty({str:None})

    comments = RelationProperty('Comment')

    def commit(self):
        VersionedArtifact.commit(self)
        if self.version > 1:
            t1 = self.upsert(self.title, self.version-1).text
            t2 = self.text
            description = h.diff_text(t1, t2)
        else:
            description = None
        Feed.post(self, description)

    def url(self):
        return self.app_config.url() + str(self.ticket_num) + '/'

    def shorthand_id(self):
        return '#' + str(self.ticket_num)

    def index(self):
        result = VersionedArtifact.index(self)
        result.update(
            title_s='Ticket %s' % self.ticket_num,
            version_i=self.version,
            type_s=self.type_s,
            ticket_num_i=self.ticket_num,
            summary_t=self.summary,
            milestone_s=self.milestone,
            status_s=self.status,
            text=self.description)
        for k,v in self.custom_fields.iteritems():
            result[k + '_s'] = str(v)
        return result

    def reported_by(self):
        return User.query.get(_id=self.reported_by_id) or User.anonymous

    def assigned_to(self):
        if self.assigned_to_id is None: return None
        return User.query.get(_id=self.assigned_to_id)

    def assigned_to_name(self):
        who = self.assigned_to()
        if who is None: return 'nobody'
        return who.display_name

    @property
    def attachments(self):
        return Attachment.by_metadata(ticket_id=self._id)

    def root_comments(self):
        if '_id' in self:
            return Comment.query.find(dict(ticket_id=self._id, reply_to=None))
        else:
            return []

    def all_comments(self):
        if '_id' in self:
            return Comment.query.find(dict(ticket_id=self._id))
        else:
            return []

    def ordered_comments(self, limit=None):
        if '_id' in self:
            if limit:
                q = Comment.query.find(dict(ticket_id=self._id),limit=limit)
            else:
                q = Comment.query.find(dict(ticket_id=self._id))
            q = q.sort([('created_date', pymongo.DESCENDING)])
            return q
        else:
            return []

    def reply(self, text):
        Feed.post(self, 'Comment: %s' % text)
        c = Comment(ticket_id=self._id, text=text)
        return c

class Comment(Message):

    class __mongometa__:
        name = 'ticket_comment'

    type_s = 'Ticket Comment'
    version = FieldProperty(0)
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)

    ticket_id = ForeignIdProperty(Ticket)
    kind = FieldProperty(str, if_missing='comment')
    reply_to_id = FieldProperty(schema.ObjectId, if_missing=None)
    text = FieldProperty(str)

    ticket = RelationProperty('Ticket')

    def index(self):
        result = Message.index(self)
        author = self.author()
        result.update(
            title_s='Comment on %s by %s' % (
                self.ticket.shorthand_id(),
                author.display_name
            ),
            type_s=self.type_s
        )
        return result

    @property
    def posted_ago(self):
        comment_td = (datetime.utcnow() - self.timestamp)
        if comment_td.seconds < 3600 and comment_td.days < 1:
            return "%s minutes ago" % (comment_td.seconds / 60)
        elif comment_td.seconds >= 3600 and comment_td.days < 1:
            return "%s hours ago" % (comment_td.seconds / 3600)
        elif comment_td.days >= 1 and comment_td.days < 7:
            return "%s days ago" % comment_td.days
        elif comment_td.days >= 7 and comment_td.days < 30:
            return "%s weeks ago" % (comment_td.days / 7)
        elif comment_td.days >= 30 and comment_td.days < 365:
            return "%s months ago" % (comment_td.days / 30)
        else:
            return "%s years ago" % (comment_td.days / 365)

    def url(self):
        return self.ticket.url() + '#comment-' + str(self._id)

    def shorthand_id(self):
        return '%s-%s' % (self.ticket.shorthand_id, self._id)

    def reply(self, text):
        r = Message.reply(self)
        r.text = text
        Feed.post(self.ticket, 'Comment: %s', text)
        return r

class Attachment(File):
    class __mongometa__:
        name = 'attachment.files'
        indexes = [
            'metadata.filename',
            'metadata.ticket_id' ]

    # Override the metadata schema here
    metadata=FieldProperty(dict(
            ticket_id=schema.ObjectId,
            app_config_id=schema.ObjectId,
            filename=str))

    @property
    def ticket(self):
        return Ticket.query.get(_id=self.metadata.ticket_id)

    def url(self):
        return self.ticket.url() + 'attachment/' + self.filename

MappedClass.compile_all()
