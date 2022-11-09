#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import logging
import six.moves.urllib.request
import six.moves.urllib.parse
import six.moves.urllib.error
import json
import difflib
from datetime import datetime, timedelta
import os
import typing

from bson import ObjectId
import six

import pymongo
from pymongo.errors import OperationFailure
from tg import tmpl_context as c, app_globals as g
from paste.deploy.converters import aslist, asbool
import jinja2
import markupsafe

from ming import schema
from ming.utils import LazyProperty
from ming.orm import Mapper, session
from ming.orm import FieldProperty, ForeignIdProperty, RelationProperty
from ming.orm.declarative import MappedClass
from ming.orm.ormsession import ThreadLocalORMSession

from tg import config as tg_config

from allura.model import (
    ACE,
    DENY_ALL,

    AppConfig,
    Artifact,
    BaseAttachment,
    Feed,
    Mailbox,
    MovedArtifact,
    Notification,
    ProjectRole,
    Snapshot,
    Thread,
    User,
    VersionedArtifact,
    VotableArtifact,

    artifact_orm_session,
    project_orm_session,
    AlluraUserProperty,
    Shortlink
)
from allura.model.timeline import ActivityObject
from allura.model.notification import MailFooter
from allura.model.types import MarkdownCache, EVERYONE

from allura.lib import security
from allura.lib.search import search_artifact, SearchError
from allura.lib import utils
from allura.lib import helpers as h
from allura.lib.plugin import ImportIdConverter
from allura.lib.security import require_access
from allura.tasks import mail_tasks
from forgetracker import search as tsearch

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


log = logging.getLogger(__name__)

CUSTOM_FIELD_SOLR_TYPES = dict(boolean='_b', number='_d')
SOLR_TYPE_DEFAULTS = dict(_b=False, _d=0)


def get_default_for_solr_type(solr_type):
    return SOLR_TYPE_DEFAULTS.get(solr_type, '')


config = utils.ConfigProxy(
    common_suffix='forgemail.domain',
    new_solr='solr.use_new_types')


class Globals(MappedClass):

    class __mongometa__:
        name = 'globals'
        session = project_orm_session
        indexes = ['app_config_id']

    query: 'Query[Globals]'

    type_s = 'Globals'

    _id = FieldProperty(schema.ObjectId)
    app_config_id = ForeignIdProperty(
        AppConfig, if_missing=lambda: c.app.config._id)
    app_config = RelationProperty(AppConfig, via='app_config_id')
    last_ticket_num = FieldProperty(int)
    status_names = FieldProperty(str)
    open_status_names = FieldProperty(str)
    closed_status_names = FieldProperty(str)
    milestone_names = FieldProperty(str, if_missing='')
    custom_fields = FieldProperty([{str: None}])
    _bin_counts = FieldProperty(schema.Deprecated)  # {str:int})
    _bin_counts_data = FieldProperty([dict(summary=str, hits=int)])
    _bin_counts_expire = FieldProperty(datetime)
    _bin_counts_invalidated = FieldProperty(datetime)
    # [dict(name=str,hits=int,closed=int)])
    _milestone_counts = FieldProperty(schema.Deprecated)
    _milestone_counts_expire = FieldProperty(schema.Deprecated)  # datetime)
    show_in_search = FieldProperty({str: bool}, if_missing={'ticket_num': True,
                                                            'summary': True,
                                                            '_milestone': True,
                                                            'status': True,
                                                            'assigned_to': True,
                                                            'reported_by': False,
                                                            'created_date': True,
                                                            'mod_date': True,
                                                            'labels': False,
                                                            })

    def next_ticket_num(self):
        gbl = Globals.query.find_and_modify(
            query=dict(app_config_id=self.app_config_id),
            update={'$inc': {'last_ticket_num': 1}},
            new=True)
        session(gbl).expunge(gbl)
        return gbl.last_ticket_num

    @property
    def all_status_names(self):
        return ' '.join([self.open_status_names, self.closed_status_names])

    @property
    def set_of_all_status_names(self):
        return {name for name in self.all_status_names.split(' ') if name}

    @property
    def set_of_open_status_names(self):
        return {name for name in self.open_status_names.split(' ') if name}

    @property
    def set_of_closed_status_names(self):
        return {name for name in self.closed_status_names.split(' ') if name}

    @property
    def not_closed_query(self):
        return ' && '.join(['!status:' + name for name in sorted(self.set_of_closed_status_names)])

    @property
    def not_closed_mongo_query(self):
        return dict(
            status={'$nin': sorted(self.set_of_closed_status_names)})

    @property
    def closed_query(self):
        return ' OR '.join(['status:' + name for name in sorted(self.set_of_closed_status_names)])

    @property
    def milestone_fields(self):
        return [fld for fld in self.custom_fields if fld['type'] == 'milestone']

    def get_custom_field(self, name):
        for fld in self.custom_fields:
            if fld['name'] == name:
                return fld
        return None

    def get_custom_field_solr_type(self, field_name):
        """Return the Solr type for a custom field.

        :param field_name: Name of the custom field
        :type field_name: str
        :returns: The Solr type suffix (e.g. '_s', '_i', '_b') or None if
            there is no custom_field named ``field_name``.

        """
        fld = self.get_custom_field(field_name)
        if fld:
            return CUSTOM_FIELD_SOLR_TYPES.get(fld.type, '_s')
        return None

    def update_bin_counts(self):
        # Refresh bin counts
        self._bin_counts_data = []
        for b in Bin.query.find(dict(
                app_config_id=self.app_config_id)):
            if b.terms and '$USER' in b.terms:
                # skip queries with $USER variable, hits will be inconsistent
                # for them
                continue
            r = search_artifact(Ticket, b.terms, rows=0, short_timeout=False, fq=['-deleted_b:true'])
            hits = r is not None and r.hits or 0
            self._bin_counts_data.append(dict(summary=b.summary, hits=hits))
        cache_expire_config = int(tg_config.get('forgetracker.bin_cache_expire', 60))
        if cache_expire_config:
            self._bin_counts_expire = datetime.utcnow() + timedelta(minutes=cache_expire_config)
        self._bin_counts_invalidated = None

    def bin_count(self, name):
        # not sure why we expire bin counts even if unchanged
        # I guess a catch-all in case invalidate_bin_counts is missed
        cache_expire_config = int(tg_config.get('forgetracker.bin_cache_expire', 60))
        if cache_expire_config and (not self._bin_counts_expire or self._bin_counts_expire < datetime.utcnow()):
            self.invalidate_bin_counts()
        for d in self._bin_counts_data:
            if d['summary'] == name:
                return d
        return dict(summary=name, hits=0)

    def milestone_count(self, name):
        fld_name, m_name = name.split(':', 1)
        d = dict(name=name, hits=0, closed=0)
        if not (fld_name and m_name):
            return d
        mongo_query = {
            'custom_fields.%s' % fld_name: m_name,
            'app_config_id': self.app_config_id,
            'deleted': False
        }
        d['hits'] = Ticket.query.find(dict(mongo_query, acl=[])).count()
        d['closed'] = Ticket.query.find(dict(mongo_query, acl=[],
                                             status={'$in': list(self.set_of_closed_status_names)})).count()

        secured_tickets = Ticket.query.find(dict(mongo_query, acl={"$ne": []}))
        if secured_tickets.count():
            tickets = [t for t in secured_tickets if security.has_access(t, 'read')]
            d['hits'] += len(tickets)
            d['closed'] += sum(1 for t in tickets if t.status in self.set_of_closed_status_names)
        return d

    def invalidate_bin_counts(self):
        '''Force expiry of bin counts and queue them to be updated.'''
        # To prevent multiple calls to this method from piling on redundant
        # tasks, we set _bin_counts_invalidated when we post the task, and
        # the task clears it when it's done.  However, in the off chance
        # that the task fails or is interrupted, we ignore the flag if it's
        # older than 5 minutes.
        delay = int(tg_config.get('forgetracker.bin_invalidate_delay', 5))
        invalidation_expiry = datetime.utcnow() - timedelta(minutes=delay)
        if self._bin_counts_invalidated is not None and \
           self._bin_counts_invalidated > invalidation_expiry:
            return
        self._bin_counts_invalidated = datetime.utcnow()
        from forgetracker import tasks  # prevent circular import
        tasks.update_bin_counts.post(self.app_config_id, delay=delay)

    def sortable_custom_fields_shown_in_search(self):
        def solr_type(field_name):
            # Pre solr-4.2.1 code indexed all custom fields as strings, so
            # they must be searched as such.
            if not config.get_bool('new_solr'):
                return '_s'
            return self.get_custom_field_solr_type(field_name) or '_s'

        return [dict(
            sortable_name='{}{}'.format(field['name'],
                solr_type(field['name'])),
            name=field['name'],
            label=field['label'])
            for field in self.custom_fields
            if field.get('show_in_search')]

    def has_deleted_tickets(self):
        return Ticket.query.find(dict(
            app_config_id=self.app_config_id, deleted=True)).count() > 0

    def move_tickets(self, ticket_ids, destination_tracker_id):
        tracker = AppConfig.query.get(_id=destination_tracker_id)
        tickets = Ticket.query.find(dict(
            _id={'$in': [ObjectId(id) for id in ticket_ids]},
            app_config_id=self.app_config_id)).sort('ticket_num').all()
        filtered = self.filtered_by_subscription({t._id: t for t in tickets})
        original_ticket_nums = {t._id: t.ticket_num for t in tickets}
        users = User.query.find({'_id': {'$in': list(filtered.keys())}}).all()
        moved_tickets = {}
        for ticket in tickets:
            moved = ticket.move(tracker, notify=False)
            moved_tickets[moved._id] = moved
        mail = dict(
            sender=c.project.app_instance(self.app_config).email_address,
            fromaddr=str(c.user.email_address_header()),
            reply_to=str(c.user.email_address_header()),
            subject='[{}:{}] Mass ticket moving by {}'.format(c.project.shortname,
                                                              self.app_config.options.mount_point,
                                                              c.user.display_name))
        tmpl = g.jinja2_env.get_template(
            'forgetracker:data/mass_move_report.html')

        tmpl_context = {
            'original_tracker': '{}:{}'.format(c.project.shortname,
                                               self.app_config.options.mount_point),
            'destination_tracker': '{}:{}'.format(tracker.project.shortname,
                                                  tracker.options.mount_point),
            'tickets': [],
        }
        for user in users:
            tmpl_context['tickets'] = ({
                'original_num': original_ticket_nums[_id],
                'destination_num': moved_tickets[_id].ticket_num,
                'summary': moved_tickets[_id].summary
            } for _id in filtered.get(user._id, []))
            mail.update(dict(
                message_id=h.gen_message_id(),
                text=tmpl.render(tmpl_context),
                destinations=[str(user._id)]))
            mail_tasks.sendmail.post(**mail)

        if self.app_config.options.get('TicketMonitoringType') in (
                'AllTicketChanges', 'AllPublicTicketChanges'):
            monitoring_email = self.app_config.options.get(
                'TicketMonitoringEmail')
            tmpl_context['tickets'] = [{
                'original_num': original_ticket_nums[_id],
                'destination_num': moved_tickets[_id].ticket_num,
                'summary': moved_tickets[_id].summary
            } for _id, t in moved_tickets.items()
                if (not t.private or
                    self.app_config.options.get('TicketMonitoringType') ==
                    'AllTicketChanges')]
            if len(tmpl_context['tickets']) > 0:
                mail.update(dict(
                    message_id=h.gen_message_id(),
                    text=tmpl.render(tmpl_context),
                    destinations=[monitoring_email]))
                mail_tasks.sendmail.post(**mail)

        moved_from = '{}/{}'.format(c.project.shortname,
                                    self.app_config.options.mount_point)
        moved_to = '{}/{}'.format(tracker.project.shortname,
                                  tracker.options.mount_point)
        text = f'Tickets moved from {moved_from} to {moved_to}'
        Notification.post_user(c.user, None, 'flash', text=text)

    def update_tickets(self, **post_data):
        from forgetracker.tracker_main import get_change_text, get_label
        tickets = Ticket.query.find(dict(
            _id={'$in': [ObjectId(id)
                         for id in aslist(
                             post_data['__ticket_ids'])]},
            app_config_id=self.app_config_id)).all()

        fields = {'status', 'private'}
        values = {}
        labels = post_data.get('labels', [])

        for k in fields:
            v = post_data.get(k)
            if v:
                values[k] = v
        assigned_to = post_data.get('assigned_to')
        if assigned_to == '-':
            values['assigned_to_id'] = None
        elif assigned_to:
            user = c.project.user_in_project(assigned_to)
            if user:
                values['assigned_to_id'] = user._id
        private = post_data.get('private')
        if private:
            values['private'] = asbool(private)

        deleted = post_data.get('deleted')
        if deleted:
            values['deleted'] = asbool(deleted)

        discussion_disabled = post_data.get('discussion_disabled')
        if discussion_disabled:
            values['disabled_discussion'] = asbool(discussion_disabled)

        custom_values = {}
        custom_fields = {}
        for cf in self.custom_fields or []:
            v = post_data.get(cf.name)
            if v:
                custom_values[cf.name] = v
                custom_fields[cf.name] = cf

        changes = {}
        changed_tickets = {}
        for ticket in tickets:
            message = ''
            if labels:
                values['labels'] = self.append_new_labels(ticket.labels, labels.split(','))
            for k, v in sorted(values.items()):
                if k == 'deleted':
                    if v:
                        ticket.soft_delete()
                        break
                elif k == 'assigned_to_id':
                    new_user = User.query.get(_id=v)
                    old_user = User.query.get(_id=getattr(ticket, k))
                    if new_user:
                        message += get_change_text(
                            get_label(k),
                            new_user.display_name,
                            old_user.display_name)
                elif k == 'private' or k == 'discussion_disabled':
                    def _text(val):
                        if val:
                            return 'Yes'
                        else:
                            return 'No'

                    message += get_change_text(
                        get_label(k),
                        _text(v),
                        _text(getattr(ticket, k)))
                else:
                    message += get_change_text(
                        get_label(k),
                        v,
                        getattr(ticket, k))
                setattr(ticket, k, v)
            for k, v in sorted(custom_values.items()):
                def cf_val(cf):
                    return ticket.get_custom_user(cf.name) \
                        if cf.type == 'user' \
                        else ticket.custom_fields.get(cf.name)
                cf = custom_fields[k]
                old_value = cf_val(cf)
                if cf.type == 'boolean':
                    v = asbool(v)
                ticket.custom_fields[k] = v
                new_value = cf_val(cf)
                message += get_change_text(
                    cf.label,
                    new_value,
                    old_value)
            if message != '':
                changes[ticket._id] = message
                changed_tickets[ticket._id] = ticket
                ticket.discussion_thread.post(message, notify=False, is_meta=True)
                ticket.commit()

        filtered_changes = self.filtered_by_subscription(changed_tickets)
        users = User.query.find(
            {'_id': {'$in': list(filtered_changes.keys())}}).all()

        def changes_iter(user):
            for t_id in filtered_changes.get(user._id, []):
                # mark changes text as safe, thus it wouldn't be escaped in plain-text emails
                # html part of email is handled by markdown and it'll be
                # properly escaped
                yield (changed_tickets[t_id], markupsafe.Markup(changes[t_id]))
        mail = dict(
            sender=c.project.app_instance(self.app_config).email_address,
            fromaddr=str(c.user._id),
            reply_to=tg_config['forgemail.return_path'],
            subject='[{}:{}] Mass edit changes by {}'.format(c.project.shortname,
                                                             self.app_config.options.mount_point,
                                                             c.user.display_name),
        )
        tmpl = g.jinja2_env.get_template('forgetracker:data/mass_report.html')
        head = []
        for f, v in sorted(values.items()):
            if f == 'assigned_to_id':
                user = User.query.get(_id=v)
                v = user.display_name if user else v
            head.append(f'- **{get_label(f)}**: {v}')
        for f, v in sorted(custom_values.items()):
            cf = custom_fields[f]
            if cf.type == 'user':
                user = User.by_username(v)
                v = user.display_name if user else v
            head.append(f'- **{cf.label}**: {v}')
        tmpl_context = {'context': c, 'data':
                        {'header': markupsafe.Markup('\n'.join(['Mass edit changing:', ''] + head))}}
        for user in users:
            tmpl_context['data'].update({'changes': changes_iter(user)})
            mail.update(dict(
                message_id=h.gen_message_id(),
                text=tmpl.render(tmpl_context),
                destinations=[str(user._id)]))
            mail_tasks.sendmail.post(**mail)

        if self.app_config.options.get('TicketMonitoringType') in (
                'AllTicketChanges', 'AllPublicTicketChanges'):
            monitoring_email = self.app_config.options.get(
                'TicketMonitoringEmail')
            visible_changes = []
            for t_id, t in changed_tickets.items():
                if (not t.private or
                        self.app_config.options.get('TicketMonitoringType') ==
                        'AllTicketChanges'):
                    visible_changes.append(
                        (changed_tickets[t_id], markupsafe.Markup(changes[t_id])))
            if visible_changes:
                tmpl_context['data'].update({'changes': visible_changes})
                mail.update(dict(
                    message_id=h.gen_message_id(),
                    text=tmpl.render(tmpl_context),
                    destinations=[monitoring_email]))
                mail_tasks.sendmail.post(**mail)

        self.invalidate_bin_counts()
        ThreadLocalORMSession.flush_all()
        app = '{}/{}'.format(c.project.shortname,
                             self.app_config.options.mount_point)
        count = len(tickets)
        text = 'Updated {} ticket{} in {}'.format(
            count, 's' if count != 1 else '', app)
        Notification.post_user(c.user, None, 'flash', text=text)

    def filtered_by_subscription(self, tickets, project_id=None, app_config_id=None):
        p_id = project_id if project_id else c.project._id
        ac_id = app_config_id if app_config_id else self.app_config_id
        ticket_ids = list(tickets.keys())
        tickets_index_id = {
            ticket.index_id(): t_id for t_id, ticket in tickets.items()}
        subscriptions = Mailbox.query.find({
            'project_id': p_id,
            'app_config_id': ac_id,
            'artifact_index_id': {'$in': list(tickets_index_id.keys()) + [None]}})
        filtered = {}
        for subscription in subscriptions:
            if subscription.artifact_index_id is None:
                # subscribed to entire tool, will see all changes
                filtered[subscription.user_id] = set(ticket_ids)
            elif subscription.artifact_index_id in list(tickets_index_id.keys()):
                user = filtered.setdefault(subscription.user_id, set())
                user.add(tickets_index_id[subscription.artifact_index_id])
        return filtered

    def append_new_labels(self, old_labels, new_labels):
        # append without duplicating any.  preserve order
        labels = old_labels[:]  # make copy to ensure no edits to possible underlying model field
        for label in new_labels:
            label = label.strip()
            if label not in old_labels:
                labels.append(label)
        return labels


class TicketHistory(Snapshot):

    class __mongometa__:
        name = 'ticket_history'

    query: 'Query[TicketHistory]'

    def original(self):
        return Ticket.query.get(_id=self.artifact_id)

    def shorthand_id(self):
        orig = self.original()
        if not orig:
            return None
        return f'{orig.shorthand_id()}#{self.version}'

    def url(self):
        orig = self.original()
        if not orig:
            return None
        return orig.url() + '?version=%d' % self.version

    @property
    def assigned_to(self):
        if self.data.assigned_to_id is None:
            return None
        return User.query.get(_id=self.data.assigned_to_id)

    def index(self):
        orig = self.original()
        if not orig:
            return None
        result = Snapshot.index(self)
        result.update(
            title='Version %d of %s' % (
                self.version, orig.summary),
            type_s='Ticket Snapshot',
            text=self.data.summary)
        # Tracker uses search with default solr parser. It would match only on
        # `text`, so we're appending all other field values into `text`, to match on it too.
        result['text'] += '\n'.join([str(v)
                                     for k, v
                                     in result.items()
                                     if k not in ('id', 'project_id_s')
                                     ])
        return result


class Bin(Artifact, ActivityObject):

    class __mongometa__:
        name = 'bin'

    query: 'Query[Bin]'

    type_s = 'Bin'

    _id = FieldProperty(schema.ObjectId)
    summary = FieldProperty(str, required=True, allow_none=False)
    terms = FieldProperty(str, if_missing='')
    sort = FieldProperty(str, if_missing='')

    @property
    def activity_name(self):
        return 'search bin %s' % self.summary

    def url(self):
        base = self.app_config.url() + 'search/?'
        params = dict(q=(h.really_unicode(self.terms).encode('utf-8') or ''))
        if self.sort:
            params['sort'] = self.sort
        return base + six.moves.urllib.parse.urlencode(params)

    def shorthand_id(self):
        return self.summary

    def index(self):
        result = Artifact.index(self)
        result.update(
            type_s=self.type_s,
            summary_t=self.summary,
            terms_s=self.terms)
        return result

    def __json__(self):
        return dict(
            _id=self._id,
            summary=self.summary,
            terms=self.terms,
            sort=self.sort,
        )


class Ticket(VersionedArtifact, ActivityObject, VotableArtifact):

    class __mongometa__:
        name = 'ticket'
        history_class = TicketHistory
        indexes = [
            'ticket_num',
            ('app_config_id', 'custom_fields._milestone'),
            'import_id',
        ]
        unique_indexes = [
            ('app_config_id', 'ticket_num'),
        ]

    query: 'Query[Ticket]'

    type_s = 'Ticket'

    _id = FieldProperty(schema.ObjectId)
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)

    ticket_num = FieldProperty(int, required=True, allow_none=False)
    summary = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    description_cache = FieldProperty(MarkdownCache)
    reported_by_id: ObjectId = AlluraUserProperty(if_missing=lambda: c.user._id)
    assigned_to_id: ObjectId = AlluraUserProperty(if_missing=None)
    milestone = FieldProperty(str, if_missing='')
    status = FieldProperty(str, if_missing='')
    custom_fields = FieldProperty({str: None})

    reported_by = RelationProperty(User, via='reported_by_id')

    def link_text(self):
        text = super().link_text()
        if self.is_closed:
            return markupsafe.Markup('<s>') + text + markupsafe.Markup('</s>')
        return text

    @property
    def activity_name(self):
        return 'ticket #%s' % self.ticket_num

    @property
    def activity_extras(self):
        d = ActivityObject.activity_extras.fget(self)
        d.update(summary=self.summary)
        return d

    @classmethod
    def new(cls, form_fields=None):
        '''Create a new ticket, safely (ensuring a unique ticket_num)'''
        while True:
            ticket_num = c.app.globals.next_ticket_num()
            ticket = cls(
                app_config_id=c.app.config._id,
                custom_fields=dict(),
                ticket_num=ticket_num)
            if form_fields:
                ticket.update_fields_basics(form_fields)
            try:
                session(ticket).flush(ticket)
                return ticket
            except OperationFailure as err:
                if 'duplicate' in err.args[0]:
                    log.warning('Try to create duplicate ticket %s',
                                ticket.url())
                    session(ticket).expunge(ticket)
                    continue
                raise

    def index(self):
        result = VersionedArtifact.index(self)
        result.update(
            title='Ticket #%d: %s' % (self.ticket_num, self.summary),
            version_i=self.version,
            type_s=self.type_s,
            created_date_dt=self.created_date,
            ticket_num_i=self.ticket_num,
            summary_t=self.summary,
            milestone_s=self.milestone,
            status_s=self.status,
            text=self.description,
            snippet_s=self.summary,
            private_b=self.private,
            discussion_disabled_b=self.discussion_disabled,
            votes_up_i=self.votes_up,
            votes_down_i=self.votes_down,
            votes_total_i=(self.votes_up - self.votes_down),
            import_id_s=ImportIdConverter.get().simplify(self.import_id)
        )
        for k, v in self.custom_fields.items():
            # Pre solr-4.2.1 code expects all custom fields to be indexed
            # as strings.
            if not config.get_bool('new_solr'):
                result[k + '_s'] = str(v)

            # Now let's also index with proper Solr types.
            solr_type = self.app.globals.get_custom_field_solr_type(k)
            if solr_type:
                result[k + solr_type] = (v or
                                         get_default_for_solr_type(solr_type))

        result['reported_by_s'] = self.reported_by.username if self.reported_by else None
        result['assigned_to_s'] = self.assigned_to.username if self.assigned_to else None

        # Tracker uses search with default solr parser. It would match only on
        # `text`, so we're appending all other field values into `text`, to
        # match on it too.
        result['text'] += '\n'.join([str(v)
                                     for k, v
                                     in result.items()
                                     if k not in ('id', 'project_id_s')
                                     ])
        return result

    @classmethod
    def attachment_class(cls):
        return TicketAttachment

    @classmethod
    def translate_query(cls, q, fields):
        q = super().translate_query(q, fields)
        cf = [f.name for f in c.app.globals.custom_fields]
        solr_field = '{0}{1}'
        solr_type = '_s'
        for f in cf:
            # Solr 4.2.1 index contains properly typed custom fields, so we
            # can search on those instead of the old string-type solr fields.
            if config.get_bool('new_solr'):
                solr_type = (c.app.globals.get_custom_field_solr_type(f)
                             or solr_type)
            actual = solr_field.format(f, solr_type)
            q = q.replace(f + ':', actual + ':')
        return q

    @property
    def _milestone(self):
        milestone = None
        for fld in self.globals.milestone_fields:
            if fld.name == '_milestone':
                return self.custom_fields.get('_milestone', '')
        return milestone

    @property
    def assigned_to(self):
        if self.assigned_to_id is None:
            return None
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
        if self.discussion_disabled:
            return tg_config.get('forgemail.return_path')
        if c.app.config.options.get('AllowEmailPosting', True):
            domain = self.email_domain
            return f'{self.ticket_num}@{domain}{config.common_suffix}'
        else:
            return tg_config.get('forgemail.return_path')

    @property
    def email_subject(self):
        return f'#{self.ticket_num} {self.summary}'

    @LazyProperty
    def globals(self):
        return Globals.query.get(app_config_id=self.app_config_id)

    @property
    def open_or_closed(self):
        return 'closed' if self.status in self.app.globals.set_of_closed_status_names else 'open'

    @property
    def is_closed(self):
        return self.open_or_closed == 'closed'

    @property
    def monitoring_email(self):
        return self.app_config.options.get('TicketMonitoringEmail')

    @property
    def notify_post(self):
        monitoring_type = self.app_config.options.get('TicketMonitoringType')
        return monitoring_type == 'AllTicketChanges' or (
            monitoring_type == 'AllPublicTicketChanges' and
            not self.private)

    def get_custom_user(self, custom_user_field_name):
        fld = None
        for f in c.app.globals.custom_fields:
            if f.name == custom_user_field_name:
                fld = f
                break
        if not fld:
            raise KeyError('Custom field "%s" does not exist.' % custom_user_field_name)
        if fld.type != 'user':
            raise TypeError('Custom field "{}" is of type "{}"; expected type "user".'.format(
                custom_user_field_name, fld.type))
        username = self.custom_fields.get(custom_user_field_name)
        if not username:
            return None
        user = self.app_config.project.user_in_project(username)
        if user == User.anonymous():
            return None
        return user

    def _get_private(self):
        return bool(self.acl)

    def _set_private(self, bool_flag):
        if bool_flag:
            role_developer = ProjectRole.by_name('Developer')
            role_creator = ProjectRole.by_user(self.reported_by, upsert=True) if self.reported_by else None

            def _allow_all(role, perms):
                return [ACE.allow(role._id, perm) for perm in sorted(perms)]  # sorted just for consistency (for tests)
            # maintain existing access for developers and the ticket creator,
            # but revoke all access for everyone else
            acl = _allow_all(role_developer, security.all_allowed(self, role_developer))
            if role_creator and role_creator != ProjectRole.anonymous():
                acl += _allow_all(role_creator, security.all_allowed(self, role_creator))
            acl += [DENY_ALL]
            self.acl = acl
        else:
            self.acl = []
    private = property(_get_private, _set_private)

    def _set_discussion_disabled(self, is_disabled):
        """ Sets a ticket's discussion thread ACL to control a users ability to post.

        :param is_disabled: If True, an explicit deny will be created on the discussion thread ACL.
        """
        if is_disabled:
            self.discussion_thread.acl = [ACE.deny(EVERYONE, 'post'),
                                          ACE.deny(EVERYONE, 'unmoderated_post')]
        else:
            self.discussion_thread.acl = []

    def _get_discussion_disabled(self):
        """ Checks the discussion thread ACL to determine if users are allowed to post."""
        thread = Thread.query.get(ref_id=self.index_id())
        if thread:
            return bool(thread.acl)
        return False
    discussion_disabled = property(_get_discussion_disabled, _set_discussion_disabled)

    def commit(self, subscribe=False, **kwargs):
        VersionedArtifact.commit(self)
        monitoring_email = self.app.config.options.get('TicketMonitoringEmail')
        if self.version > 1:
            hist = TicketHistory.query.get(
                artifact_id=self._id, version=self.version - 1)
            old = hist.data
            changes = ['Ticket {} has been modified: {}'.format(
                self.ticket_num, self.summary),
                'Edited By: {} ({})'.format(c.user.get_pref('display_name'), c.user.username)]
            fields = [
                ('Summary', old.summary, self.summary),
                ('Status', old.status, self.status)]
            if old.status != self.status and self.status in c.app.globals.set_of_closed_status_names:
                g.statsUpdater.ticketEvent(
                    "closed", self, self.project, self.assigned_to)
            for key in self.custom_fields:
                fields.append(
                    (key, old.custom_fields.get(key, ''), self.custom_fields[key]))
            for title, o, n in fields:
                if o != n:
                    changes.append('{} updated: {!r} => {!r}'.format(
                        title, o, n))
            o = hist.assigned_to
            n = self.assigned_to
            if o != n:
                changes.append('Owner updated: {!r} => {!r}'.format(
                    o and o.username, n and n.username))
                self.subscribe(user=n)
                g.statsUpdater.ticketEvent("assigned", self, self.project, n)
                if o:
                    g.statsUpdater.ticketEvent(
                        "revoked", self, self.project, o)
            if old.description != self.description:
                changes.append('Description updated:')
                changes.append('\n'.join(
                    difflib.unified_diff(
                        a=old.description.split('\n'),
                        b=self.description.split('\n'),
                        fromfile='description-old',
                        tofile='description-new')))
            description = '\n'.join(changes)
        else:
            if subscribe:
                self.subscribe()
            if self.assigned_to_id:
                user = User.query.get(_id=self.assigned_to_id)
                g.statsUpdater.ticketEvent(
                    "assigned", self, self.project, user)
                self.subscribe(user=user)
            description = ''
            subject = self.email_subject
            Thread.new(discussion_id=self.app_config.discussion_id,
                       ref_id=self.index_id())
            # First ticket notification. Use persistend Message-ID (self.message_id()).
            # Thus we can group notification emails in one thread later.
            n = Notification.post(
                message_id=self.message_id(),
                artifact=self,
                topic='metadata',
                text=description,
                subject=subject)
            if monitoring_email and n and (not self.private or
                                           self.app.config.options.get('TicketMonitoringType') in (
                                               'NewTicketsOnly', 'AllTicketChanges')):
                n.send_simple(monitoring_email)
        Feed.post(
            self,
            title=self.summary,
            description=description if description else self.description,
            author=self.reported_by,
            pubdate=self.created_date)

    def url(self):
        return self.app_config.url() + str(self.ticket_num) + '/'

    def shorthand_id(self):
        return '#' + str(self.ticket_num)

    def assigned_to_name(self):
        who = self.assigned_to
        if who in (None, User.anonymous()):
            return 'nobody'
        return who.get_pref('display_name')

    def update_fields_basics(self, ticket_form):
        # "simple", non-persisting updates.  Must be safe to call within the Ticket.new() while its creating it

        # update is not allowed to change the ticket_num
        ticket_form.pop('ticket_num', None)
        self.labels = ticket_form.pop('labels', [])
        custom_users = set()
        other_custom_fields = set()
        for cf in self.globals.custom_fields or []:
            (custom_users if cf['type'] == 'user' else
             other_custom_fields).add(cf['name'])
            if cf['type'] == 'boolean' and 'custom_fields.' + cf['name'] not in ticket_form:
                self.custom_fields[cf['name']] = 'False'
        # this has to happen because the milestone custom field has special
        # layout treatment
        if '_milestone' in ticket_form:
            other_custom_fields.add('_milestone')
            milestone = ticket_form.pop('_milestone', None)
            if 'custom_fields' not in ticket_form:
                ticket_form['custom_fields'] = dict()
            ticket_form['custom_fields']['_milestone'] = milestone
        for k, v in ticket_form.items():
            if k == 'assigned_to':
                if v:
                    user = c.project.user_in_project(v)
                    if user:
                        self.assigned_to_id = user._id
            elif k in ('subscribe', 'attachment'):
                # handled separately in update_fields_finish()
                pass
            else:
                setattr(self, k, v)
        if 'custom_fields' in ticket_form:
            for k, v in ticket_form['custom_fields'].items():
                if k in custom_users:
                    # restrict custom user field values to project members
                    user = self.app_config.project.user_in_project(v)
                    self.custom_fields[k] = user.username \
                        if user and user != User.anonymous() else ''
                elif k in other_custom_fields:
                    # strings are good enough for any other custom fields
                    self.custom_fields[k] = v

    def update_fields_finish(self, ticket_form):
        attachment = None
        if 'attachment' in ticket_form:
            attachment = ticket_form.pop('attachment')
        if attachment is not None:
            self.add_multiple_attachments(attachment)
            # flush the session to make attachments available in the
            # notification email
            ThreadLocalORMSession.flush_all()
        subscribe = ticket_form.pop('subscribe', False)
        self.commit(subscribe=subscribe)

    def update(self, ticket_form):
        self.update_fields_basics(ticket_form)
        self.update_fields_finish(ticket_form)

    def _move_attach(self, attachments, attach_metadata, app_config):
        for attach in attachments:
            attach.app_config_id = app_config._id
            if attach.attachment_type == 'DiscussionAttachment':
                attach.discussion_id = app_config.discussion_id
            attach_thumb = BaseAttachment.query.get(
                filename=attach.filename, **attach_metadata)
            if attach_thumb:
                if attach_thumb.attachment_type == 'DiscussionAttachment':
                    attach_thumb.discussion_id = app_config.discussion_id
                attach_thumb.app_config_id = app_config._id

    def move(self, app_config, notify=True):
        '''Move ticket from current tickets app to tickets app with given app_config'''
        app = app_config.project.app_instance(app_config)
        prior_url = self.url()
        prior_app = self.app
        prior_ticket_num = self.ticket_num
        attachments = self.attachments
        attach_metadata = BaseAttachment.metadata_for(self)
        prior_cfs = [
            (cf['name'], cf['type'], cf['label'])
            for cf in prior_app.globals.custom_fields or []]
        new_cfs = [
            (cf['name'], cf['type'], cf['label'])
            for cf in app.globals.custom_fields or []]
        skipped_fields = []
        user_fields = []
        for cf in prior_cfs:
            if cf not in new_cfs:  # can't convert
                skipped_fields.append(cf)
            elif cf[1] == 'user':  # can convert and field type == user
                user_fields.append(cf)
        messages = []
        for cf in skipped_fields:
            name = cf[0]
            messages.append('- **%s**: %s' %
                            (name, self.custom_fields.get(name, '')))
        for cf in user_fields:
            name = cf[0]
            username = self.custom_fields.get(name, None)
            user = app_config.project.user_in_project(username)
            if not user or user == User.anonymous():
                messages.append('- **%s**: %s (user not in project)' %
                                (name, username))
                self.custom_fields[name] = ''
        # special case: not custom user field (assigned_to_id)
        user = self.assigned_to
        if user and not app_config.project.user_in_project(user.username):
            messages.append('- **assigned_to**: %s (user not in project)' %
                            user.username)
            self.assigned_to_id = None

        custom_fields = {}
        for cf in new_cfs:
            fn, ft, fl = cf
            old_val = self.custom_fields.get(fn, None)
            if old_val is None:
                custom_fields[fn] = None if ft == 'user' else ''
            custom_fields[fn] = old_val
        self.custom_fields = custom_fields

        # move ticket. ensure unique ticket_num
        while True:
            with h.push_context(app_config.project_id, app_config_id=app_config._id):
                ticket_num = app.globals.next_ticket_num()
            self.ticket_num = ticket_num
            self.app_config_id = app_config._id
            new_url = app_config.url() + str(self.ticket_num) + '/'
            try:
                session(self).flush(self)
                break
            except OperationFailure as err:
                if 'duplicate' in err.args[0]:
                    log.warning(
                        'Try to create duplicate ticket %s when moving from %s' %
                        (new_url, prior_url))
                    session(self).expunge(self)
                    continue

        attach_metadata['type'] = 'thumbnail'
        self._move_attach(attachments, attach_metadata, app_config)

        # move ticket's discussion thread, thus all new comments will go to a
        # new ticket's feed
        self.discussion_thread.app_config_id = app_config._id
        self.discussion_thread.discussion_id = app_config.discussion_id
        for post in self.discussion_thread.posts:
            attach_metadata = BaseAttachment.metadata_for(post)
            attach_metadata['type'] = 'thumbnail'
            self._move_attach(post.attachments, attach_metadata, app_config)
            post.app_config_id = app_config._id
            post.app_id = app_config._id
            post.discussion_id = app_config.discussion_id

        session(self.discussion_thread).flush(self.discussion_thread)
        # need this to reset app_config RelationProperty on ticket to a new one
        session(self.discussion_thread).expunge(self.discussion_thread)
        session(self).expunge(self)
        ticket = Ticket.query.find(dict(
            app_config_id=app_config._id, ticket_num=self.ticket_num)).first()

        # move individual subscriptions
        # (may cause an unnecessary subscription if user is already subscribed to destination tool)
        Mailbox.query.update({
            'artifact_index_id': ticket.index_id(),  # this is unique
            'project_id': prior_app.project._id,  # include this to use an index
        }, {'$set': {
            'project_id': app_config.project_id,
            'app_config_id': app_config._id,
            'artifact_url': ticket.url(),
            'artifact_title': h.get_first(ticket.index(), 'title'),
        }}, multi=True)
        # create subscriptions for 'All artifacts' tool-level subscriptions
        tool_subs = Mailbox.query.find({'project_id': prior_app.project._id,
                                        'app_config_id': prior_app.config._id,
                                        'artifact_index_id': None,
                                        }).all()
        for tool_sub in tool_subs:
            Mailbox.subscribe(user_id=tool_sub.user_id, project_id=app_config.project_id, app_config_id=app_config._id,
                              artifact=ticket)

        # creating MovedTicket to be able to redirect from this url
        moved_ticket = MovedTicket(
            app_config_id=prior_app.config._id, ticket_num=prior_ticket_num,
            moved_to_url=ticket.url(),
        )

        message = 'Ticket moved from %s' % prior_url
        if messages:
            message += '\n\nCan\'t be converted:\n\n'
        message += '\n'.join(messages)
        with h.push_context(ticket.project_id, app_config_id=app_config._id):
            ticket.discussion_thread.add_post(text=message, notify=notify)
        return ticket

    def attachments_for_export(self):
        return [dict(bytes=attach.length,
                     url=h.absurl(attach.url()),
                     path=os.path.join(
                         self.app_config.options.mount_point,
                         str(self._id),
                         os.path.basename(attach.filename))) for attach in self.attachments]

    def attachments_for_json(self):
        return [dict(bytes=attach.length,
                     url=h.absurl(attach.url())) for attach in self.attachments]

    def __json__(self, posts_limit=None, is_export=False):
        parents_json = {}
        for parent in reversed(type(self).mro()):
            if parent != type(self) and hasattr(parent, '__json__'):
                kwargs = {}
                if parent == VersionedArtifact:
                    kwargs['posts_limit'] = posts_limit
                try:
                    parents_json.update(parent.__json__(self, is_export=is_export, **kwargs))
                except Exception:
                    parents_json.update(parent.__json__(self, **kwargs))

        return dict(parents_json,
                    created_date=self.created_date,
                    ticket_num=self.ticket_num,
                    summary=self.summary,
                    description=self.description,
                    reported_by=self.reported_by_username,
                    assigned_to=self.assigned_to_id and self.assigned_to_username or None,
                    reported_by_id=self.reported_by_id and str(
                        self.reported_by_id) or None,
                    assigned_to_id=self.assigned_to_id and str(
                        self.assigned_to_id) or None,
                    status=self.status,
                    private=self.private,
                    discussion_disabled=self.discussion_disabled,
                    attachments=self.attachments_for_export() if is_export else self.attachments_for_json(),
                    custom_fields=dict(self.custom_fields))

    @classmethod
    def paged_query(cls, app_config, user, query, limit=None, page=0, sort=None, deleted=False, **kw):
        """
        Query tickets, filtering for 'read' permission, sorting and paginating the result.

        See also paged_search which does a solr search
        """
        limit, page, start = g.handle_paging(limit, page, default=25)
        q = cls.query.find(
            dict(query, app_config_id=app_config._id, deleted=deleted))
        q = q.sort('ticket_num', pymongo.DESCENDING)
        if sort and ' ' in sort:
            field, direction = sort.split()
            if field.startswith('_'):
                field = 'custom_fields.' + field
            direction = dict(
                asc=pymongo.ASCENDING,
                desc=pymongo.DESCENDING)[direction]
            q = q.sort(field, direction)
        q = q.skip(start)
        q = q.limit(limit)
        tickets = []
        count = q.count()
        for t in q:
            if security.has_access(t, 'read', user, app_config.project.root_project):
                tickets.append(t)
            else:
                count = count - 1

        return dict(
            tickets=tickets,
            count=count, q=json.dumps(query), limit=limit, page=page, sort=sort,
            **kw)

    @classmethod
    def paged_search(cls, app_config, user, q, limit=None, page=0, sort=None, show_deleted=False,
                     filter=None, **kw):
        """Query tickets from Solr, filtering for 'read' permission, sorting and paginating the result.

        See also paged_query which does a mongo search.

        We do the sorting and skipping right in SOLR, before we ever ask
        Mongo for the actual tickets.  Other keywords for
        search_artifact (e.g., history) or for SOLR are accepted through
        kw.  The output is intended to be used directly in templates,
        e.g., exposed controller methods can just:

            return paged_query(q, ...)

        If you want all the results at once instead of paged you have
        these options:
          - don't call this routine, search directly in mongo
          - call this routine with a very high limit and TEST that
            count<=limit in the result
        limit=-1 is NOT recognized as 'all'.  500 is a reasonable limit.
        """

        limit, page, start = g.handle_paging(limit, page, default=25)
        count = 0
        tickets = []
        if filter is None:
            filter = {}
        refined_sort = sort if sort else 'ticket_num_i desc'
        if 'ticket_num_i' not in refined_sort:
            refined_sort += ',ticket_num_i asc'
        try:
            if q:
                # also query for choices for filter options right away
                params = kw.copy()
                params.update(tsearch.FACET_PARAMS)
                if not show_deleted:
                    params['fq'] = ['deleted_b:False']

                matches = search_artifact(
                    cls, q, short_timeout=True,
                    rows=limit, sort=refined_sort, start=start, fl='id',
                    filter=filter, **params)
            else:
                matches = None
            solr_error = None
        except SearchError as e:
            solr_error = e
            matches = None
        if matches:
            count = matches.hits
            # ticket_matches is in sorted order
            ticket_matches = [ObjectId(match['id'].split('#')[1]) for match in matches.docs]
            query = cls.query.find(
                dict(_id={'$in': ticket_matches}))
            # so stick all the results in a dictionary...
            ticket_by_id = {}
            for t in query:
                ticket_by_id[t._id] = t
            # and pull them out in the order given by ticket_numbers
            tickets = []
            for t_id in ticket_matches:
                if t_id in ticket_by_id:
                    show_deleted = show_deleted and security.has_access(
                        ticket_by_id[t_id], 'delete', user, app_config.project.root_project)
                    if (security.has_access(ticket_by_id[t_id], 'read', user,
                                            app_config.project.root_project if app_config else None) and
                            (show_deleted or ticket_by_id[t_id].deleted is False)):
                        tickets.append(ticket_by_id[t_id])
                    else:
                        count = count - 1
        return dict(tickets=tickets,
                    count=count, q=q, limit=limit, page=page, sort=sort,
                    filter=filter,
                    filter_choices=tsearch.get_facets(matches),
                    solr_error=solr_error, **kw)

    @classmethod
    def paged_query_or_search(cls, app_config, user, query, search_query, filter,
                              limit=None, page=0, sort=None, **kw):
        """Switch between paged_query and paged_search based on filter.

        query - query in mongo syntax
        search_query - query in solr syntax
        """
        solr_sort = None
        if sort and ' ' in sort:
            from forgetracker.tracker_main import _mongo_col_to_solr_col
            sort_split = sort.split(' ')
            solr_col = _mongo_col_to_solr_col(sort_split[0])
            solr_sort = f'{solr_col} {sort_split[1]}'
        if not filter:
            result = cls.paged_query(app_config, user, query, sort=sort, limit=limit, page=page, **kw)
            t = cls.query.find().first()
            if t:
                search_query = cls.translate_query(search_query, t.index())
            result['filter_choices'] = tsearch.query_filter_choices(
                search_query, fq=[] if kw.get('show_deleted', False) else ['deleted_b:False'])
        else:
            result = cls.paged_search(app_config, user, search_query, filter=filter,
                                      sort=solr_sort, limit=limit, page=page, **kw)

        result['sort'] = sort
        result['url_sort'] = solr_sort if solr_sort else ''
        return result

    def get_mail_footer(self, notification, toaddr):
        if toaddr and toaddr == self.monitoring_email:
            return MailFooter.monitored(
                toaddr,
                h.absurl(self.app.url),
                h.absurl('{}admin/{}/options'.format(
                    self.project.url(),
                    self.app.config.options.mount_point)))
        return MailFooter.standard(
            notification,
            self.app.config.options.get('AllowEmailPosting', True),
            discussion_disabled=self.discussion_disabled)

    def soft_delete(self):
        require_access(self, 'delete')
        Shortlink.query.remove(dict(ref_id=self.index_id()))
        self.deleted = True
        suffix = " {dt.hour}:{dt.minute}:{dt.second} {dt.day}-{dt.month}-{dt.year}".format(
            dt=datetime.utcnow())
        self.summary += suffix
        c.app.globals.invalidate_bin_counts()


class TicketAttachment(BaseAttachment):
    thumbnail_size = (100, 100)
    ArtifactType = Ticket

    class __mongometa__:
        polymorphic_identity = 'TicketAttachment'

    query: 'Query[TicketAttachment]'

    attachment_type = FieldProperty(str, if_missing='TicketAttachment')


class MovedTicket(MovedArtifact):

    class __mongometa__:
        session = artifact_orm_session
        name = 'moved_ticket'
        indexes = [
            ('app_config_id', 'ticket_num'),
        ]

    query: 'Query[MovedTicket]'

    ticket_num = FieldProperty(int, required=True, allow_none=False)

    def url(self):
        return self.moved_to_url


Mapper.compile_all()
