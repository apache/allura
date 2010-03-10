from time import sleep
from datetime import datetime

import tg
from pylons import c
from pymongo.errors import OperationFailure
import pymongo

from ming import schema
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, ForeignIdProperty, RelationProperty
from datetime import datetime

from pyforge.model import Artifact, VersionedArtifact, Snapshot, Message, project_orm_session, Project
from pyforge.model import File, User, Feed, Thread, Post
from pyforge.lib import helpers as h

common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')

class Globals(MappedClass):

    class __mongometa__:
        name = 'globals'
        session = project_orm_session

    type_s = 'Globals'
    _id = FieldProperty(schema.ObjectId)
    app_config_id = ForeignIdProperty('AppConfig', if_missing=lambda:c.app.config._id)
    last_ticket_num = FieldProperty(int)
    status_names = FieldProperty(str)
    custom_fields = FieldProperty([{str:None}])

class TicketHistory(Snapshot):

    class __mongometa__:
        name = 'ticket_history'

    def original(self):
        return Ticket.query.get(_id=self.artifact_id)

    def shorthand_id(self):
        return '%s#%s' % (self.original().shorthand_id(), self.version)

    def url(self):
        return self.original().url() + '?version=%d' % self.version

    def assigned_to(self):
        if self.data.assigned_to_id is None: return None
        return User.query.get(_id=self.data.assigned_to_id)

    def index(self):
        result = Snapshot.index(self)
        result.update(
            title_s='Version %d of %s' % (
                self.version,self.original().summary),
            type_s='Ticket Snapshot',
            text=self.data.summary)
        return result

class Bin(Artifact):
    class __mongometa__:
        name = 'bin'

    type_s = 'Bin'
    _id = FieldProperty(schema.ObjectId)
    summary = FieldProperty(str)
    terms = FieldProperty(str, if_missing='')

    def url(self):
        return self.app_config.url() + 'search/?q=' + str(self.terms)

    def shorthand_id(self):
        return 'bin(' + str(self.summary) + ')'

    def index(self):
        result = Artifact.index(self)
        result.update(
            type_s=self.type_s,
            summary_t=self.summary,
            terms_s=self.terms)
        return result

class Ticket(VersionedArtifact):
    class __mongometa__:
        name = 'ticket'
        history_class = TicketHistory

    type_s = 'Ticket'
    _id = FieldProperty(schema.ObjectId)
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)

    super_id = FieldProperty(schema.ObjectId, if_missing=None)
    sub_ids = FieldProperty([schema.ObjectId], if_missing=None)
    ticket_num = FieldProperty(int)
    summary = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    reported_by_id = FieldProperty(schema.ObjectId, if_missing=lambda:c.user._id)
    assigned_to_id = FieldProperty(schema.ObjectId, if_missing=None)
    milestone = FieldProperty(str, if_missing='')
    status = FieldProperty(str, if_missing='')
    custom_fields = FieldProperty({str:None})

    # comments = RelationProperty('Comment')

    @property
    def email_address(self):
        domain = '.'.join(reversed(self.app.url[1:-1].split('/')))
        return '%s@%s%s' % (self.ticket_num, domain, common_suffix)

    def commit(self):
        VersionedArtifact.commit(self)
        if self.version > 1:
            hist = TicketHistory.query.get(artifact_id=self._id, version=self.version-1)
            old = hist.data
            changes = []
            fields = [
                ('Summary', old.summary, self.summary),
                ('Status', old.status, self.status) ]
            for key in self.custom_fields:
                fields.append((key, old.custom_fields.get(key, ''), self.custom_fields[key]))
            for title, o, n in fields:
                if o != n:
                    changes.append('%s updated: %r => %r' % (
                            title, o, n))
            o = hist.assigned_to()
            n = self.assigned_to()
            if o != n:
                changes.append('Owner updated: %r => %r' % (
                        o and o.username, n and n.username))
            if old.description != self.description:
                changes.append('Description updated:')
                changes.append(h.diff_text(old.description, self.description))
            description = '<br>'.join(changes)
        else:
            description = 'Ticket %s created: %s' % (
                self.ticket_num, self.summary)
            Thread(discussion_id=self.app_config.discussion_id,
                   artifact_id=self._id,
                   subject='#%s discussion' % self.ticket_num)

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
        return Attachment.by_metadata(ticket_id=self._id,type='attachment')

    # def root_comments(self):
    #     if '_id' in self:
    #         return Comment.query.find(dict(ticket_id=self._id, reply_to=None))
    #     else:
    #         return []

    # def all_comments(self):
    #     if '_id' in self:
    #         return Comment.query.find(dict(ticket_id=self._id))
    #     else:
    #         return []

    # def ordered_comments(self, limit=None):
    #     if '_id' in self:
    #         if limit:
    #             q = Comment.query.find(dict(ticket_id=self._id),limit=limit)
    #         else:
    #             q = Comment.query.find(dict(ticket_id=self._id))
    #         q = q.sort([('created_date', pymongo.DESCENDING)])
    #         return q
    #     else:
    #         return []

    # def reply(self, text):
    #     Feed.post(self, 'Comment: %s' % text)
    #     c = Comment(ticket_id=self._id, text=text)
    #     return c

    def set_as_subticket_of(self, new_super_id):
        # For this to be generally useful we would have to check first that
        # new_super_id is not a sub_id (recursively) of self

        if self.super_id == new_super_id:
            return

        if self.super_id is not None:
            old_super = Ticket.query.get(_id=self.super_id, app_config_id=c.app.config._id)
            old_super.sub_ids = [id for id in old_super.sub_ids if id != self._id]
            old_super.dirty_sums(dirty_self=True)

        self.super_id = new_super_id

        if new_super_id is not None:
            new_super = Ticket.query.get(_id=new_super_id, app_config_id=c.app.config._id)
            if new_super.sub_ids is None:
                new_super.sub_ids = []
            if self._id not in new_super.sub_ids:
                new_super.sub_ids.append(self._id)
            new_super.dirty_sums(dirty_self=True)

    def recalculate_sums(self, super_sums=None):
        """Calculate custom fields of type 'sum' (if any) by recursing into subtickets (if any)."""
        if super_sums is None:
            super_sums = {}
            globals = Globals.query.get(app_config_id=c.app.config._id)
            for k in [cf.name for cf in globals.custom_fields or [] if cf.type=='sum']:
                super_sums[k] = float(0)

        # if there are no custom fields of type 'sum', we're done
        if not super_sums:
            return

        # if this ticket has no subtickets, use its field values directly
        if not self.sub_ids:
            for k in super_sums:
                try:
                    v = float(self.custom_fields.get(k, 0))
                except ValueError:
                    v = 0
                super_sums[k] += v

        # else recurse into subtickets
        else:
            sub_sums = {}
            for k in super_sums:
                sub_sums[k] = float(0)
            for id in self.sub_ids:
                subticket = Ticket.query.get(_id=id, app_config_id=c.app.config._id)
                subticket.recalculate_sums(sub_sums)
            for k, v in sub_sums.iteritems():
                self.custom_fields[k] = v
                super_sums[k] += v

    def dirty_sums(self, dirty_self=False):
        """From a changed ticket, climb the superticket chain to call recalculate_sums at the root."""
        root = self if dirty_self else None
        next_id = self.super_id
        while next_id is not None:
            root = Ticket.query.get(_id=next_id, app_config_id=c.app.config._id)
            next_id = root.super_id
        if root is not None:
            root.recalculate_sums()


# class Comment(Message):

#     class __mongometa__:
#         name = 'ticket_comment'

#     type_s = 'Ticket Comment'
#     version = FieldProperty(0)
#     created_date = FieldProperty(datetime, if_missing=datetime.utcnow)

#     ticket_id = ForeignIdProperty(Ticket)
#     kind = FieldProperty(str, if_missing='comment')
#     reply_to_id = FieldProperty(schema.ObjectId, if_missing=None)
#     text = FieldProperty(str)

#     ticket = RelationProperty('Ticket')

#     def index(self):
#         result = Message.index(self)
#         author = self.author()
#         result.update(
#             title_s='Comment on %s by %s' % (
#                 self.ticket.shorthand_id(),
#                 author.display_name
#             ),
#             type_s=self.type_s
#         )
#         return result

#     @property
#     def posted_ago(self):
#         comment_td = (datetime.utcnow() - self.timestamp)
#         if comment_td.seconds < 3600 and comment_td.days < 1:
#             return "%s minutes ago" % (comment_td.seconds / 60)
#         elif comment_td.seconds >= 3600 and comment_td.days < 1:
#             return "%s hours ago" % (comment_td.seconds / 3600)
#         elif comment_td.days >= 1 and comment_td.days < 7:
#             return "%s days ago" % comment_td.days
#         elif comment_td.days >= 7 and comment_td.days < 30:
#             return "%s weeks ago" % (comment_td.days / 7)
#         elif comment_td.days >= 30 and comment_td.days < 365:
#             return "%s months ago" % (comment_td.days / 30)
#         else:
#             return "%s years ago" % (comment_td.days / 365)

#     def url(self):
#         return self.ticket.url() + '#comment-' + str(self._id)

#     def shorthand_id(self):
#         return '%s-%s' % (self.ticket.shorthand_id, self._id)

#     def reply(self, text):
#         r = Message.reply(self)
#         r.text = text
#         Feed.post(self.ticket, 'Comment: %s', text)
#         return r

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
            type=str,
            filename=str))

    @property
    def ticket(self):
        return Ticket.query.get(_id=self.metadata.ticket_id)

    def url(self):
        return self.ticket.url() + 'attachment/' + self.filename

MappedClass.compile_all()
