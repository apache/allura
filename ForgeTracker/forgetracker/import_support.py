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
from ming.orm import session

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

    def parse_date(self, date_string):
        return datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%SZ')

    def make_user_placeholder(self, username):
        user = M.User.register(dict(username=username,
                                   display_name=username), False)
        ThreadLocalORMSession.flush_all()
        logging.info('Created user: %s', user._id)
        return user

    def make_artifact(self, ticket_dict):
        FIELD_NAME_MAP = {
          'date': ('created_date', self.parse_date), 
          'date_updated': ('mod_date', self.parse_date), 
          'keywords': ('labels', lambda s: s.split()),
          'version': (None, None),
        }
        remapped = {}
        for f, v in ticket_dict.iteritems():
            f, conv = FIELD_NAME_MAP.get(f, (f, lambda x:x))
            if f:
                remapped[f] = conv(v)

        log.info('==========Calling constr============')
        ticket = TM.Ticket(
            app_config_id=c.app.config._id,
            custom_fields=dict(),
            ticket_num=c.app.globals.next_ticket_num(), mod_date=remapped['mod_date'])
        log.info('==========Calling update============')
        ticket.update(remapped)
        log.info('==========Setting in_migr============')
        log.info('==========Calling save============')
#        session(ticket).save(ticket)
        return ticket

    def make_comment(self, thread, comment_dict):
        ts = self.parse_date(comment_dict['date'])
        comment = thread.post(text=comment_dict['comment'], timestamp=ts)
        user = M.User.by_username(comment_dict['submitter'])
        if not user:
            log.warning('Unknown user %s during comment import', comment_dict['submitter'])
            # XXX: created mostly for debugging
            user = self.make_user_placeholder(comment_dict['submitter'])
            comment.author_id = user._id
        else:
            comment.author_id = user._id

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

    def perform_import(self, doc):
#        log.info('migrate called: %s', doc) 
        M.session.artifact_orm_session._get().skip_mod_date = True
        artifacts = json.loads(doc)
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
