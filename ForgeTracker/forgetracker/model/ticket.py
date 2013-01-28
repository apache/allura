import logging
import urllib
import json
import difflib
from datetime import datetime, timedelta

import pymongo
import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pymongo.errors import OperationFailure
from pylons import c, g

from ming import schema
from ming.utils import LazyProperty
from ming.orm import Mapper, session
from ming.orm import FieldProperty, ForeignIdProperty, RelationProperty
from ming.orm.declarative import MappedClass

from allura.model import (Artifact, VersionedArtifact, Snapshot,
                          project_orm_session, BaseAttachment, VotableArtifact)
from allura.model import User, Feed, Thread, Notification, ProjectRole
from allura.model import ACE, ALL_PERMISSIONS, DENY_ALL
from allura.model.timeline import ActivityObject

from allura.lib import security
from allura.lib.search import search_artifact
from allura.lib import utils
from allura.lib import helpers as h

from forgetracker.plugins import ImportIdConverter

log = logging.getLogger(__name__)

config = utils.ConfigProxy(
    common_suffix='forgemail.domain')

class Globals(MappedClass):

    class __mongometa__:
        name = 'globals'
        session = project_orm_session
        indexes = [ 'app_config_id' ]

    type_s = 'Globals'
    _id = FieldProperty(schema.ObjectId)
    app_config_id = ForeignIdProperty('AppConfig', if_missing=lambda:c.app.config._id)
    last_ticket_num = FieldProperty(int)
    status_names = FieldProperty(str)
    open_status_names = FieldProperty(str)
    closed_status_names = FieldProperty(str)
    milestone_names = FieldProperty(str, if_missing='')
    custom_fields = FieldProperty([{str:None}])
    _bin_counts = FieldProperty(schema.Deprecated) # {str:int})
    _bin_counts_data = FieldProperty([dict(summary=str, hits=int)])
    _bin_counts_expire = FieldProperty(datetime)
    _milestone_counts = FieldProperty([dict(name=str,hits=int,closed=int)])
    _milestone_counts_expire = FieldProperty(datetime)
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

    @classmethod
    def next_ticket_num(cls):
        gbl = cls.query.find_and_modify(
            query=dict(app_config_id=c.app.config._id),
            update={'$inc': { 'last_ticket_num': 1}},
            new=True)
        session(cls).expunge(gbl)
        return gbl.last_ticket_num

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
    def not_closed_mongo_query(self):
        return dict(
            status={'$nin': list(self.set_of_closed_status_names)})

    @property
    def closed_query(self):
        return ' or '.join(['status:'+name for name in self.set_of_closed_status_names])

    @property
    def milestone_fields(self):
        return [ fld for fld in self.custom_fields if fld['type'] == 'milestone' ]

    def get_custom_field(self, name):
        for fld in self.custom_fields:
            if fld['name'] == name:
                return fld
        return None

    def _refresh_counts(self):
        # Refresh bin counts
        self._bin_counts_data = []
        for b in Bin.query.find(dict(
                app_config_id=self.app_config_id)):
            r = search_artifact(Ticket, b.terms, rows=0)
            hits = r is not None and r.hits or 0
            self._bin_counts_data.append(dict(summary=b.summary, hits=hits))
        self._bin_counts_expire = \
            datetime.utcnow() + timedelta(minutes=60)

    def bin_count(self, name):
        if self._bin_counts_expire < datetime.utcnow():
            self._refresh_counts()
        for d in self._bin_counts_data:
            if d['summary'] == name: return d
        return dict(summary=name, hits=0)

    def milestone_count(self, name):
        fld_name, m_name = name.split(':', 1)
        d = dict(name=name, hits=0, closed=0)
        if not (fld_name and m_name):
            return d
        mongo_query = {'custom_fields.%s' % fld_name: m_name}
        r = Ticket.query.find(dict(
            mongo_query, app_config_id=c.app.config._id, deleted=False))
        tickets = [t for t in r if security.has_access(t, 'read')]
        d['hits'] = len(tickets)
        d['closed'] = sum(1 for t in tickets
                          if t.status in c.app.globals.set_of_closed_status_names)
        return d

    def invalidate_bin_counts(self):
        '''Expire it just a bit in the future to allow data to propagate through
        the search task
        '''
        self._bin_counts_expire = datetime.utcnow() + timedelta(seconds=5)

    def sortable_custom_fields_shown_in_search(self):
        return [dict(sortable_name='%s_s' % field['name'],
                     name=field['name'],
                     label=field['label'])
                for field in self.custom_fields
                if field.get('show_in_search')]

    def has_deleted_tickets(self):
        return  Ticket.query.find(dict(
            app_config_id=c.app.config._id, deleted=True)).count() > 0


class TicketHistory(Snapshot):

    class __mongometa__:
        name = 'ticket_history'

    def original(self):
        return Ticket.query.get(_id=self.artifact_id)

    def shorthand_id(self):
        orig = self.original()
        if not orig:
            return None
        return '%s#%s' % (orig.shorthand_id(), self.version)

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
            title_s='Version %d of %s' % (
                self.version, orig.summary),
            type_s='Ticket Snapshot',
            text=self.data.summary)
        return result

class Bin(Artifact, ActivityObject):
    class __mongometa__:
        name = 'bin'

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

class Ticket(VersionedArtifact, ActivityObject, VotableArtifact):
    class __mongometa__:
        name = 'ticket'
        history_class = TicketHistory
        indexes = [
            'ticket_num',
            'app_config_id',
            ('app_config_id', 'custom_fields._milestone'),
            'import_id',
            ]
        unique_indexes = [
            ('app_config_id', 'ticket_num'),
            ]

    type_s = 'Ticket'
    _id = FieldProperty(schema.ObjectId)
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)

    ticket_num = FieldProperty(int, required=True, allow_none=False)
    summary = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    reported_by_id = ForeignIdProperty(User, if_missing=lambda:c.user._id)
    assigned_to_id = ForeignIdProperty(User, if_missing=None)
    milestone = FieldProperty(str, if_missing='')
    status = FieldProperty(str, if_missing='')
    custom_fields = FieldProperty({str:None})

    reported_by = RelationProperty(User, via='reported_by_id')

    @property
    def activity_name(self):
        return 'ticket #%s' % self.ticket_num

    @classmethod
    def new(cls):
        '''Create a new ticket, safely (ensuring a unique ticket_num'''
        while True:
            ticket_num = c.app.globals.next_ticket_num()
            ticket = cls(
                app_config_id=c.app.config._id,
                custom_fields=dict(),
                ticket_num=ticket_num)
            try:
                session(ticket).flush(ticket)
                h.log_action(log, 'opened').info('')
                return ticket
            except OperationFailure, err:
                if 'duplicate' in err.args[0]:
                    log.warning('Try to create duplicate ticket %s', ticket.url())
                    session(ticket).expunge(ticket)
                    continue
                raise

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
            snippet_s=self.summary,
            votes_up_i=self.votes_up,
            votes_down_i=self.votes_down,
            votes_total_i=(self.votes_up-self.votes_down),
            import_id_s=ImportIdConverter.get().simplify(self.import_id)
            )
        for k,v in self.custom_fields.iteritems():
            result[k + '_s'] = unicode(v)
        if self.reported_by:
            result['reported_by_s'] = self.reported_by.username
        if self.assigned_to:
            result['assigned_to_s'] = self.assigned_to.username
        return result

    @classmethod
    def attachment_class(cls):
        return TicketAttachment

    @classmethod
    def translate_query(cls, q, fields):
        q = super(Ticket, cls).translate_query(q, fields)
        cf = [f.name for f in c.app.globals.custom_fields]
        for f in cf:
            actual = '_%s_s' % f[1:]
            base = f
            q = q.replace(base+':', actual+':')
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
        return '%s@%s%s' % (self.ticket_num, domain, config.common_suffix)

    @property
    def email_subject(self):
        return '#%s %s' % (self.ticket_num, self.summary)

    @LazyProperty
    def globals(self):
        return Globals.query.get(app_config_id=self.app_config_id)

    @property
    def open_or_closed(self):
        return 'closed' if self.status in c.app.globals.set_of_closed_status_names else 'open'

    @property
    def monitoring_email(self):
        return c.app.config.options.get('TicketMonitoringEmail')

    @property
    def notify_post(self):
        return c.app.config.options.get('TicketMonitoringType') == 'AllTicketChanges'

    def get_custom_user(self, custom_user_field_name):
        fld = None
        for f in c.app.globals.custom_fields:
            if f.name == custom_user_field_name:
                fld = f
                break
        if not fld:
            raise KeyError, 'Custom field "%s" does not exist.' % custom_user_field_name
        if fld.type != 'user':
            raise TypeError, 'Custom field "%s" is of type "%s"; expected ' \
                             'type "user".' % (custom_user_field_name, fld.type)
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
            role_developer = ProjectRole.by_name('Developer')._id
            role_creator = self.reported_by.project_role()._id
            self.acl = [
                ACE.allow(role_developer, ALL_PERMISSIONS),
                ACE.allow(role_creator, ALL_PERMISSIONS),
                DENY_ALL]
        else:
            self.acl = []
    private = property(_get_private, _set_private)

    def commit(self):
        VersionedArtifact.commit(self)
        monitoring_email = self.app.config.options.get('TicketMonitoringEmail')
        if self.version > 1:
            hist = TicketHistory.query.get(artifact_id=self._id, version=self.version-1)
            old = hist.data
            changes = ['Ticket %s has been modified: %s' % (
                    self.ticket_num, self.summary),
                       'Edited By: %s (%s)' % (c.user.get_pref('display_name'), c.user.username)]
            fields = [
                ('Summary', old.summary, self.summary),
                ('Status', old.status, self.status) ]
            if old.status != self.status and self.status in c.app.globals.set_of_closed_status_names:
                h.log_action(log, 'closed').info('')
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
                        difflib.unified_diff(
                            a=old.description.split('\n'),
                            b=self.description.split('\n'),
                            fromfile='description-old',
                            tofile='description-new')))
            description = '\n'.join(changes)
        else:
            self.subscribe()
            if self.assigned_to_id:
                self.subscribe(user=User.query.get(_id=self.assigned_to_id))
            description = ''
            subject = self.email_subject
            Thread.new(discussion_id=self.app_config.discussion_id,
                   ref_id=self.index_id())
            n = Notification.post(artifact=self, topic='metadata', text=description, subject=subject)
            if monitoring_email and n:
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
        if who in (None, User.anonymous()): return 'nobody'
        return who.get_pref('display_name')

    @property
    def attachments(self):
        return TicketAttachment.query.find(dict(
            app_config_id=self.app_config_id, artifact_id=self._id, type='attachment'))

    def update(self, ticket_form):
        self.globals.invalidate_bin_counts()
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
        # this has to happen because the milestone custom field has special layout treatment
        if '_milestone' in ticket_form:
            other_custom_fields.add('_milestone')
            milestone = ticket_form.pop('_milestone', None)
            if 'custom_fields' not in ticket_form:
                ticket_form['custom_fields'] = dict()
            ticket_form['custom_fields']['_milestone'] = milestone
        attachment = None
        if 'attachment' in ticket_form:
            attachment = ticket_form.pop('attachment')
        for k, v in ticket_form.iteritems():
            if k == 'assigned_to':
                if v:
                    user = c.project.user_in_project(v)
                    if user:
                        self.assigned_to_id = user._id
            else:
                setattr(self, k, v)
        if 'custom_fields' in ticket_form:
            for k,v in ticket_form['custom_fields'].iteritems():
                if k in custom_users:
                    # restrict custom user field values to project members
                    user = self.app_config.project.user_in_project(v)
                    self.custom_fields[k] = user.username \
                        if user and user != User.anonymous() else ''
                elif k in other_custom_fields:
                    # strings are good enough for any other custom fields
                    self.custom_fields[k] = v
        self.commit()
        if attachment is not None:
            self.attach(
                attachment.filename, attachment.file,
                content_type=attachment.type)

    def move(self, app_config):
        '''Move ticket from current tickets app to tickets app with given app_config'''
        app = app_config.project.app_instance(app_config)
        prior_url = self.url()
        prior_app = self.app
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
            messages.append('- **%s**: %s' % (name, self.custom_fields.get(name, '')))
        for cf in user_fields:
            name = cf[0]
            username = self.custom_fields.get(name, None)
            user = app_config.project.user_in_project(username)
            if not user or user == User.anonymous():
                messages.append('- **%s**: %s (user not in project)' % (name, username))
                self.custom_fields[name] = ''
        # special case: not custom user field (assigned_to_id)
        user = self.assigned_to
        if user and not app_config.project.user_in_project(user.username):
            messages.append('- **assigned_to**: %s (user not in project)' % user.username)
            self.assigned_to_id = None

        custom_fields = {}
        for cf in new_cfs:
            fn, ft, fl = cf
            old_val = self.custom_fields.get(fn, None)
            if old_val is None:
                custom_fields[fn] = None if ft == 'user' else ''
            custom_fields[fn] = old_val
        self.custom_fields = custom_fields

        self.globals.invalidate_bin_counts()
        # move ticket. ensure unique ticket_num
        while True:
            with h.push_context(app_config.project_id, app_config_id=app_config._id):
                ticket_num = app.globals.next_ticket_num()
            self.ticket_num = ticket_num
            self.app_config_id = app_config._id
            try:
                session(self).flush(self)
                h.log_action(log, 'moved').info('Ticket %s moved to %s' % (prior_url, self.url()))
                break
            except OperationFailure, err:
                if 'duplicate' in err.args[0]:
                    log.warning('Try to create duplicate ticket %s when moving from %s' % (self.url(), prior_url))
                    session(self).expunge(self)
                    continue
        # move ticket's discussion thread, thus all new commnets will go to a new ticket's feed
        self.discussion_thread.discussion.app_config_id = app_config._id
        self.discussion_thread.app_config_id = app_config._id
        for post in self.discussion_thread.posts:
            post.app_config_id = app_config._id
            post.app_id = app_config._id

        session(self.discussion_thread.discussion).flush(self.discussion_thread.discussion)
        session(self.discussion_thread).flush(self.discussion_thread)
        # need this to reset app_config RelationProperty on ticket to a new one
        session(self.discussion_thread.discussion).expunge(self.discussion_thread.discussion)
        session(self.discussion_thread).expunge(self.discussion_thread)
        session(self).expunge(self)
        ticket = Ticket.query.find(dict(
            app_config_id=app_config._id, ticket_num=self.ticket_num)).first()

        message = 'Ticket moved from %s' % prior_url
        if messages:
            message += '\n\nCan\'t be converted:\n\n'
        message += '\n'.join(messages)
        with h.push_context(ticket.project_id, app_config_id=app_config._id):
            ticket.discussion_thread.add_post(text=message)
        return ticket

    def __json__(self):
        return dict(super(Ticket,self).__json__(),
            created_date=self.created_date,
            ticket_num=self.ticket_num,
            summary=self.summary,
            description=self.description,
            reported_by=self.reported_by_username,
            assigned_to=self.assigned_to_username,
            reported_by_id=self.reported_by_id and str(self.reported_by_id) or None,
            assigned_to_id=self.assigned_to_id and str(self.assigned_to_id) or None,
            status=self.status,
            private=self.private,
            custom_fields=self.custom_fields)

    @classmethod
    def paged_query(cls, app_config, user, query, limit=None, page=0, sort=None, deleted=False, **kw):
        """
        Query tickets, filtering for 'read' permission, sorting and paginating the result.

        See also paged_search which does a solr search
        """
        limit, page, start = g.handle_paging(limit, page, default=25)
        q = cls.query.find(dict(query, app_config_id=app_config._id, deleted=deleted))
        q = q.sort('ticket_num')
        if sort:
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
            if security.has_access(t, 'read', user, app_config.project):
                tickets.append(t)
            else:
                count = count -1

        return dict(
            tickets=tickets,
            count=count, q=json.dumps(query), limit=limit, page=page, sort=sort,
            **kw)

    @classmethod
    def paged_search(cls, app_config, user, q, limit=None, page=0, sort=None, deleted=[False], **kw):
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
        refined_sort = sort if sort else 'ticket_num_i asc'
        if  'ticket_num_i' not in refined_sort:
            refined_sort += ',ticket_num_i asc'
        try:
            if q:
                matches = search_artifact(
                    cls, q,
                    rows=limit, sort=refined_sort, start=start, fl='ticket_num_i', **kw)
            else:
                matches = None
            solr_error = None
        except ValueError, e:
            solr_error = e.args[0]
            matches = []
        if matches:
            count = matches.hits
            # ticket_numbers is in sorted order
            ticket_numbers = [match['ticket_num_i'] for match in matches.docs]
            # but query, unfortunately, returns results in arbitrary order
            query = cls.query.find(dict(app_config_id=app_config._id, ticket_num={'$in':ticket_numbers}))
            # so stick all the results in a dictionary...
            ticket_for_num = {}
            for t in query:
                ticket_for_num[t.ticket_num] = t
            # and pull them out in the order given by ticket_numbers
            tickets = []
            for tn in ticket_numbers:
                if tn in ticket_for_num:
                    if (security.has_access(ticket_for_num[tn], 'read', user, app_config.project) and
                       (ticket_for_num[tn].deleted in deleted)):
                        tickets.append(ticket_for_num[tn])
                    else:
                        count = count -1
        return dict(tickets=tickets,
                    count=count, q=q, limit=limit, page=page, sort=sort,
                    solr_error=solr_error, **kw)

class TicketAttachment(BaseAttachment):
    thumbnail_size = (100, 100)
    ArtifactType=Ticket
    class __mongometa__:
        polymorphic_identity='TicketAttachment'
    attachment_type=FieldProperty(str, if_missing='TicketAttachment')

Mapper.compile_all()
