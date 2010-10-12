from time import sleep
from datetime import datetime, timedelta

import urllib
import tg
from pymongo import bson
from pylons import c

from ming import schema
from ming.utils import LazyProperty
from ming.orm import MappedClass, session
from ming.orm import FieldProperty, ForeignIdProperty, RelationProperty

from allura.model import Artifact, VersionedArtifact, Snapshot, Message, project_orm_session, Project, BaseAttachment
from allura.model import User, Feed, Thread, Post, Notification
from allura.lib import helpers as h
from allura.lib import patience
from allura.lib.search import search_artifact
from allura.lib.security import require, has_artifact_access

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
    open_status_names = FieldProperty(str)
    closed_status_names = FieldProperty(str)
    milestone_names = FieldProperty(str, if_missing='')
    custom_fields = FieldProperty([{str:None}])
    _bin_counts = FieldProperty({str:int})
    _bin_counts_expire = FieldProperty(datetime)

    @classmethod
    def next_ticket_num(cls):
        g = cls.query.find_and_modify(
            query=dict(app_config_id=c.app.config._id),
            update={'$inc': { 'last_ticket_num': 1}},
            new=True)
        return g.last_ticket_num+1

    @property
    def all_status_names(self):
        return ' '.join([self.open_status_names, self.closed_status_names])

    @property
    def set_of_all_status_names(self):
        return set([name for name in self.all_status_names.split(' ') if name])

    @property
    def set_of_open_status_names(self):
        return set([name for name in self.open_status_names.split(' ') if name])

    @property
    def set_of_closed_status_names(self):
        return set([name for name in self.closed_status_names.split(' ') if name])

    @property
    def not_closed_query(self):
        return ' && '.join(['!status:'+name for name in self.set_of_closed_status_names])

    @property
    def bin_counts(self):
        if self._bin_counts_expire is None or datetime.utcnow() > self._bin_counts_expire:
            for b in Bin.query.find(dict(
                    app_config_id=self.app_config_id)):
                r = search_artifact(Ticket, b.terms, rows=0)
                self._bin_counts[b.summary] = r is not None and r.hits or 0
            self._bin_counts_expire = datetime.utcnow() + timedelta(minutes=60)
        return self._bin_counts

    def invalidate_bin_counts(self):
        '''Expire it just a bit in the future to allow data to propagate through
        the search reactors
        '''
        self._bin_counts_expire = datetime.utcnow() + timedelta(seconds=5)

    def sortable_custom_fields_shown_in_search(self):
        return [dict(sortable_name='%s_s' % field['name'],
                     name=field['name'],
                     label=field['label'])
                for field in self.custom_fields
                if field.get('show_in_search')]


class TicketHistory(Snapshot):

    class __mongometa__:
        name = 'ticket_history'

    def original(self):
        return Ticket.query.get(_id=self.artifact_id)

    def shorthand_id(self):
        return '%s#%s' % (self.original().shorthand_id(), self.version)

    def url(self):
        return self.original().url() + '?version=%d' % self.version

    @property
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
    summary = FieldProperty(str, required=True)
    terms = FieldProperty(str, if_missing='')
    sort = FieldProperty(str, if_missing='')

    def url(self):
        base = self.app_config.url() + 'search/?'
        params = dict(q=(self.terms or ''))
        if self.sort:
            params['sort'] = self.sort
        return base + urllib.urlencode(params)

    def shorthand_id(self):
        return self.summary

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
        indexes = [
            'ticket_num',
            'app_config_id' ]

    type_s = 'Ticket'
    _id = FieldProperty(schema.ObjectId)
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)

    super_id = FieldProperty(schema.ObjectId, if_missing=None)
    sub_ids = FieldProperty([schema.ObjectId], if_missing=None)
    ticket_num = FieldProperty(int)
    summary = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    reported_by_id = ForeignIdProperty(User, if_missing=lambda:c.user._id)
    assigned_to_id = ForeignIdProperty(User, if_missing=None)
    milestone = FieldProperty(str, if_missing='')
    status = FieldProperty(str, if_missing='')
    custom_fields = FieldProperty({str:None})

    reported_by = RelationProperty(User, via='reported_by_id')

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
            text=self.description,
            snippet_s=self.summary)
        for k,v in self.custom_fields.iteritems():
            result[k + '_s'] = unicode(v)
        if self.reported_by:
            result['reported_by_s'] = self.reported_by.username
        if self.assigned_to:
            result['assigned_to_s'] = self.assigned_to.username
        return result

    @property
    def assigned_to(self):
        if self.assigned_to_id is None: return None
        return User.query.get(_id=self.assigned_to_id)

    @property
    def reported_by_username(self):
        if self.reported_by:
            return self.reported_by.username
        return 'nobody'

    @property
    def assigned_to_username(self):
        if self.assigned_to:
            return self.assigned_to.username
        return 'nobody'

    @property
    def email_address(self):
        domain = '.'.join(reversed(self.app.url[1:-1].split('/'))).replace('_', '-')
        return '%s@%s%s' % (self.ticket_num, domain, common_suffix)

    @LazyProperty
    def globals(self):
        return Globals.query.get(app_config_id=self.app_config_id)

    @property
    def open_or_closed(self):
        return 'closed' if self.status in c.app.globals.set_of_closed_status_names else 'open'

    def commit(self):
        VersionedArtifact.commit(self)
        if self.version > 1:
            hist = TicketHistory.query.get(artifact_id=self._id, version=self.version-1)
            old = hist.data
            changes = ['Ticket %s has been modified: %s' % (
                    self.ticket_num, self.summary),
                       'Edited By: %s (%s)' % (c.user.display_name, c.user.username)]
            fields = [
                ('Summary', old.summary, self.summary),
                ('Status', old.status, self.status) ]
            for key in self.custom_fields:
                fields.append((key, old.custom_fields.get(key, ''), self.custom_fields[key]))
            for title, o, n in fields:
                if o != n:
                    changes.append('%s updated: %r => %r' % (
                            title, o, n))
            o = hist.assigned_to
            n = self.assigned_to
            if o != n:
                changes.append('Owner updated: %r => %r' % (
                        o and o.username, n and n.username))
                self.subscribe(user=n)
            if old.description != self.description:
                changes.append('Description updated:')
                changes.append('\n'.join(
                        patience.unified_diff(
                            a=old.description.split('\n'),
                            b=self.description.split('\n'),
                            fromfile='description-old',
                            tofile='description-new')))
            description = '\n'.join(changes)
            subject = 'Ticket #%s modified by %s (%s): %s' % (
                self.ticket_num, c.user.display_name, c.user.username, self.summary)
        else:
            self.subscribe()
            if self.assigned_to_id:
                self.subscribe(user=User.query.get(_id=self.assigned_to_id))
            changes = ['Ticket %s has been created: %s' % (
                    self.ticket_num, self.summary),
                       'Created By: %s (%s)' % (c.user.display_name, c.user.username)]
            description = '\n'.join(changes)
            subject = 'Ticket #%s created by %s (%s): %s' % (
                self.ticket_num, c.user.display_name, c.user.username, self.summary)
            Thread(discussion_id=self.app_config.discussion_id,
                   artifact_reference=self.dump_ref(),
                   subject='#%s discussion' % self.ticket_num)
        Feed.post(self, description)
        Notification.post(artifact=self, topic='metadata', text=description, subject=subject)

    def url(self):
        return self.app_config.url() + str(self.ticket_num) + '/'

    def shorthand_id(self):
        return '#' + str(self.ticket_num)

    def assigned_to_name(self):
        who = self.assigned_to
        if who in (None, User.anonymous()): return 'nobody'
        return who.display_name

    @property
    def attachments(self):
        return TicketAttachment.by_metadata(ticket_id=self._id,type='attachment')

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
                except (TypeError, ValueError):
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

    def update(self,ticket_form):
        self.globals.invalidate_bin_counts()
        tags = (ticket_form.pop('tags', None) or '')
        if tags == ['']:
            tags = []
        labels = (ticket_form.pop('labels', None) or '')
        if labels == ['']:
            labels = []
        self.labels = labels
        h.tag_artifact(self, c.user, tags)
        custom_sums = set()
        other_custom_fields = set()
        for cf in self.globals.custom_fields or []:
            (custom_sums if cf.type=='sum' else other_custom_fields).add(cf.name)
            if cf.type == 'boolean' and 'custom_fields.'+cf.name not in ticket_form:
                self.custom_fields[cf.name] = 'False'
        if 'attachment' in ticket_form:
            attachments = ticket_form.pop('attachment')
            if attachments:
                for attachment in attachments:
                    self.attach(file_info=attachment)
        for k, v in ticket_form.iteritems():
            if 'custom_fields.' in k:
                k = k.split('custom_fields.')[1]
            if k in custom_sums:
                # sums must be coerced to numeric type
                try:
                    self.custom_fields[k] = float(v)
                except (TypeError, ValueError):
                    self.custom_fields[k] = 0
            elif k in other_custom_fields:
                # strings are good enough for any other custom fields
                self.custom_fields[k] = v
            elif k == 'assigned_to':
                if v:
                    user = c.project.user_in_project(v)
                    if user:
                        self.assigned_to_id = user._id
            elif k != 'super_id':
                # if it's not a custom field, set it right on the ticket (but don't overwrite super_id)
                setattr(self, k, v)
        self.commit()
        # flush so we can participate in a subticket search (if any)
        session(self).flush()
        super_id = ticket_form.get('super_id')
        if super_id:
            self.set_as_subticket_of(bson.ObjectId(super_id))

    def __json__(self):
        return dict(
            _id=str(self._id),
            created_date=self.created_date,
            super_id=str(self.super_id),
            sub_ids=[str(id) for id in self.sub_ids],
            ticket_num=self.ticket_num,
            summary=self.summary,
            description=self.description,
            reported_by=self.reported_by_username,
            assigned_to=self.assigned_to_username,
            reported_by_id=self.reported_by_id and str(self.reported_by_id) or None,
            assigned_to_id=self.assigned_to_id and str(self.assigned_to_id) or None,
            milestone=self.milestone,
            status=self.status,
            custom_fields=self.custom_fields)

class TicketAttachment(BaseAttachment):
    metadata=FieldProperty(dict(
            ticket_id=schema.ObjectId,
            app_config_id=schema.ObjectId,
            type=str,
            filename=str))

    @property
    def artifact(self):
        return Ticket.query.get(_id=self.metadata.ticket_id)

    @classmethod
    def metadata_for(cls, ticket):
        return dict(
            ticket_id=ticket._id,
            app_config_id=ticket.app_config_id)

MappedClass.compile_all()
