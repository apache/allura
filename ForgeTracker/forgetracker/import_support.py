#-*- python -*-
import logging
import json, urllib, re
from datetime import datetime, timedelta
from urllib import urlencode
from webob import exc

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import g, c, request, response
from formencode import validators
from pymongo.bson import ObjectId

from ming.orm.ormsession import ThreadLocalORMSession
from ming.orm import session, state

# Pyforge-specific imports
from allura import model as M
from allura.lib import helpers as h
from allura.app import Application, SitemapEntry, DefaultAdminController
from allura.lib.search import search_artifact
from allura.lib.decorators import audit, react
from allura.lib.security import require, has_artifact_access
from allura.lib import widgets as w
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets.subscriptions import SubscribeForm
from allura.controllers import AppDiscussionController, AppDiscussionRestController
from allura.controllers import attachments as ac
from allura.controllers import BaseController

# Local imports
from forgetracker import model as TM
from forgetracker import version

from forgetracker.widgets.ticket_form import TicketForm, TicketCustomField
from forgetracker.widgets.bin_form import BinForm
from forgetracker.widgets.ticket_search import TicketSearchResults, MassEdit, MassEditForm
from forgetracker.widgets.admin_custom_fields import TrackerFieldAdmin, TrackerFieldDisplay

log = logging.getLogger(__name__)


class ImportSupport(object):

    def __init__(self):
        # At first the idea to use Ticket introspection comes,
        # but it contains various internal fields, so we'd need
        # to define somethig explicitly anyway.
        #
        # Map JSON interchange format fields to Ticket fields
        # key is JSON's field name, value is:
        #   None - drop
        #   True - map as is
        #   (new_field_name, value_convertor(val)) - use new field name and convert JSON's value
        #   handler(ticket, field, val) - arbitrary transform, expected to modify ticket in-place
        ImportSupport.FIELD_MAP = {
            'assigned_to': ('assigned_to_id', self.get_user_id),
            'class': None,
            'date': ('created_date', self.parse_date), 
            'date_updated': ('mod_date', self.parse_date),
            'description': True,
            'id': None,
            'keywords': ('labels', lambda s: s.split()),
            'status': True,
            'submitter': ('reported_by_id', self.get_user_id),
            'summary': True,
        }


    @staticmethod
    def parse_date(date_string):
        return datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%SZ')

    @staticmethod
    def get_user_id(username):
        u = M.User.by_username(username)
        if u:
            return u._id
        return None

    def custom(self, ticket, field, value):
        field = '_' + field
        if not c.app.has_custom_field(field):
            log.warning('Custom field %s is not defined, defining as string', field)
            c.app.add_custom_field(dict(name=field, label=field[1:].capitalize(), type='string'))
            ThreadLocalORMSession.flush_all()
        if 'custom_fields' not in ticket:
            ticket['custom_fields'] = {}
        ticket['custom_fields'][field] = value

    def make_artifact(self, ticket_dict):
        remapped = {}
        for f, v in ticket_dict.iteritems():
            if f in self.FIELD_MAP:
                transform = self.FIELD_MAP[f]
                if transform is None:
                    continue
                elif transform is True:
                    remapped[f] = v
                elif callable(transform):
                    transform(remapped, f, v)
                else:
                    new_f, conv = transform
                    remapped[new_f] = conv(v)
            else:
                self.custom(remapped, f, v)

        log.info('==========Calling constr============')
        ticket = TM.Ticket(
            app_config_id=c.app.config._id,
            custom_fields=dict(),
            ticket_num=c.app.globals.next_ticket_num())
        log.info('Ticket schema: %s', ticket.__mongometa__.schema.fields)
        log.info('Ticket state doc: %s', state(ticket).document)
        log.info('==========Calling update============')
        ticket.update(remapped)
        log.info('==========Setting in_migr============')
        log.info('==========Calling save============')
#        session(ticket).save(ticket)
        return ticket

    def make_comment(self, thread, comment_dict):
        ts = self.parse_date(comment_dict['date'])
        comment = thread.post(text=comment_dict['comment'], timestamp=ts)
        comment.author_id = self.get_user_id(comment_dict['submitter'])

    def collect_users(self, artifacts):
        users = set()
        for a in artifacts:
            users.add(a['submitter'])
            users.add(a['assigned_to'])
            for c in a['comments']:
                users.add(c['submitter'])
        return users
                
    def find_unknown_users(self, users):
        unknown  = set()
        for u in users:
            if u and not M.User.by_username(u):
                unknown.add(u)
        return unknown

    def make_user_placeholders(self, usernames):
        for username in usernames:
            M.User.register(dict(username=username,
                                 display_name=username), False)
        ThreadLocalORMSession.flush_all()
        log.info('Created %d user placeholders', len(usernames))


    def validate_import(self, doc):
        log.info('validate_migration called: %s', doc)
        migrator = ImportSupport()
        errors = []
        warnings = []

        artifacts = json.loads(doc)
        users = self.collect_users(artifacts)
        unknown_users = self.find_unknown_users(users)
        unknown_users = sorted(list(unknown_users))
        errors.append('Document contains unknown users: %s' % unknown_users)
            
        return errors, warnings

    def perform_import(self, doc, create_users=True):
#        log.info('migrate called: %s', doc) 
        artifacts = json.loads(doc)
        if create_users:
            users = self.collect_users(artifacts)
            unknown_users = self.find_unknown_users(users)
            self.make_user_placeholders(unknown_users)
        
        M.session.artifact_orm_session._get().skip_mod_date = True
        log.info('users in doc: %s', self.collect_users(artifacts))
        for a in artifacts:
            comments = a['comments']
            del a['comments']
            log.info(a)
            t = self.make_artifact(a)
            log.info('Created ticket: %d', t.ticket_num)
            for c_entry in comments:
                self.make_comment(t.discussion_thread, c_entry)

        return True
