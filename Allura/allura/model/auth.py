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

from __future__ import annotations

import logging
import calendar
import typing

import six
from markupsafe import Markup
from six.moves.urllib.parse import urlparse
from email import header
from hashlib import sha256
from datetime import timedelta, datetime, time
import os
import re

from pytz import timezone
import pymongo
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
from tg import config
from tg import tmpl_context as c, app_globals as g
from tg import request
from ming import schema as S
from ming import Field
from ming.orm import session, state
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty
from ming.orm.declarative import MappedClass
from ming.orm.ormsession import ThreadLocalORMSession
from ming.utils import LazyProperty

import allura.tasks.mail_tasks
from allura.lib import helpers as h
from allura.lib import plugin
from allura.lib import utils
from allura.lib.decorators import memoize
from allura.lib.search import SearchIndexable
from .session import main_orm_session, main_explicitflush_orm_session
from .session import project_orm_session
from .timeline import ActivityNode, ActivityObject


if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query
    from allura.model.project import Project


log = logging.getLogger(__name__)


class AlluraUserProperty(ForeignIdProperty):
    '''
    Specialized ForeignIdProperty for users, specifically to set allow_none=True
    since Allura uses _id=None to represent *anonymous user, and ming
    (by default) doesn't allow a None foreign key to reference a real object
    '''

    def __init__(self, **kwargs):
        super().__init__('User', allow_none=True, **kwargs)


class EmailAddress(MappedClass):
    re_format = re.compile(r'^.*\s+<(.*)>\s*$')

    class __mongometa__:
        name = 'email_address'
        session = main_orm_session
        indexes = ['nonce', ]
        unique_indexes = [('email', 'claimed_by_user_id'), ]

    query: 'Query[EmailAddress]'

    _id = FieldProperty(S.ObjectId)
    email = FieldProperty(str)
    claimed_by_user_id = FieldProperty(S.ObjectId, if_missing=None)
    confirmed = FieldProperty(bool, if_missing=False)
    nonce = FieldProperty(str)
    valid_address = FieldProperty(bool, if_missing=None)
    valid_details = FieldProperty(S.Anything, if_missing=None)
    valid_check_date = FieldProperty(datetime, if_missing=None)

    @classmethod
    def get(cls, **kw):
        '''Equivalent to Ming's query.get but calls self.canonical on address
        before lookup. You should always use this instead of query.get'''
        if kw.get('email'):
            email = cls.canonical(kw['email'])
            if email is not None:
                kw['email'] = email
            else:
                return None
        return cls.query.get(**kw)

    @classmethod
    def find(cls, q=None):
        '''Equivalent to Ming's query.find but calls self.canonical on address
        before lookup. You should always use this instead of query.find'''
        if q:
            if q.get('email'):
                email = cls.canonical(q['email'])
                if email is not None:
                    q['email'] = email
                else:
                    return utils.EmptyCursor()
            return cls.query.find(q)
        return cls.query.find()

    def claimed_by_user(self, include_pending=False):
        q = {'_id': self.claimed_by_user_id,
             'disabled': False,
             'pending': False}
        if include_pending:
            q.pop('pending', None)
        return User.query.get(**q)

    @classmethod
    def create(cls, addr):
        addr = cls.canonical(addr)
        if addr is not None:
            return cls(email=addr)

    @classmethod
    def canonical(cls, addr):
        mo = cls.re_format.match(addr)
        if mo:
            addr = mo.group(1)
        if '@' in addr:
            try:
                user, domain = addr.strip().split('@')
                return f'{user}@{domain.lower()}'
            except ValueError:
                return addr.strip()
        else:
            return None

    def send_claim_attempt(self):
        confirmed_email = self.find(dict(email=self.email, confirmed=True)).all()

        if confirmed_email:
            log.info('Sending claim attempt email to %s', self.email)
            text = g.jinja2_env.get_template('allura:templates/mail/claimed_existing_email.txt').render(dict(
                email=self,
                user=confirmed_email[0].claimed_by_user(),
                config=config
            ))

            allura.tasks.mail_tasks.send_system_mail_to_user(self.email,
                                                             '%s - Email address claim attempt' % config['site_name'],
                                                             text)

    def set_nonce_hash(self):
        self.nonce = sha256(os.urandom(10)).hexdigest()
        return True

    def send_verification_link(self):
        self.set_nonce_hash()
        log.info('Sending verification link to %s', self.email)
        text = '''
To verify the email address %s belongs to the user %s,
please visit the following URL:

%s
''' % (self.email,
       self.claimed_by_user(include_pending=True).username,
       h.absurl(f'/auth/verify_addr?a={h.urlquote(self.nonce)}'),
       )
        log.info('Verification email:\n%s', text)
        allura.tasks.mail_tasks.sendsimplemail.post(
            fromaddr=g.noreply,
            reply_to=g.noreply,
            toaddr=self.email,
            subject='%s - Email address verification' % config['site_name'],
            message_id=h.gen_message_id(),
            text=text)


class AuthGlobals(MappedClass):
    class __mongometa__:
        name = 'auth_globals'
        session = main_orm_session

    query: 'Query[AuthGlobals]'

    _id = FieldProperty(int)
    next_uid = FieldProperty(int, if_missing=10000)

    @classmethod
    def upsert(cls):
        r = cls.query.get()
        if r is not None:
            return r
        try:
            r = cls(_id=0)
            session(r).flush(r)
            return r
        except pymongo.errors.DuplicateKeyError:  # pragma no cover
            session(r).flush(r)
            r = cls.query.get()
            return r

    @classmethod
    def get_next_uid(cls):
        cls.upsert()
        g = cls.query.find_and_modify(
            query={}, update={'$inc': {'next_uid': 1}},
            new=True)
        return g.next_uid


class FieldPropertyDisplayName(FieldProperty):
    # display_name is mongo field but only for preference storage
    # force all requests for this field to use the get_pref mechanism
    # Cache it per user, since it may be re-used several times in a request
    # and non-local preferences (ldap, database, etc) can be relatively expensive

    def __get__(self, instance, cls=None):
        if instance is None:
            return self
        try:
            display_name = instance._cache_display_name
        except AttributeError:
            display_name = instance._cache_display_name = instance.get_pref('display_name')
        return display_name


class User(MappedClass, ActivityNode, ActivityObject, SearchIndexable):
    SALT_LEN = 8

    class __mongometa__:
        name = 'user'
        session = main_orm_session
        indexes = ['tool_data.AuthPasswordReset.hash']
        unique_indexes = ['username']
        custom_indexes = [
            dict(fields=('tool_data.phone_verification.number_hash',), sparse=True),
        ]

    query: 'Query[User]'

    type_s = 'User'

    _id = FieldProperty(S.ObjectId)
    sfx_userid = FieldProperty(S.Deprecated)
    username = FieldProperty(str)
    email_addresses = FieldProperty([str])
    password = FieldProperty(str)
    last_password_updated = FieldProperty(datetime)  # to access, use AuthProvider's get_last_password_updated
    reg_date = FieldProperty(datetime)  # to access, use user.registration_date()
    projects = FieldProperty(S.Deprecated)
    # full mount point: prefs dict
    tool_preferences = FieldProperty(S.Deprecated)
    tool_data = FieldProperty({str: {str: None}})  # entry point: prefs dict
    disabled = FieldProperty(bool, if_missing=False)
    pending = FieldProperty(bool, if_missing=False)

    # Don't use these directly, use get/set_pref() instead
    preferences = FieldProperty(dict(
        results_per_page=int,
        email_address=str,
        email_format=str,
        disable_user_messages=bool,
        mention_notifications=bool,
        multifactor=bool,
        message_reply_real_address=bool,
    ))
    # Additional top-level fields can/should be accessed with get/set_pref also
    # Not sure why we didn't put them within the 'preferences' dictionary :(
    display_name: str = FieldPropertyDisplayName(str)
    # Personal data
    sex = FieldProperty(
        S.OneOf('Male', 'Female', 'Other', 'Unknown',
                if_missing='Unknown'))
    birthdate = FieldProperty(S.DateTime, if_missing=None)

    # Availability information
    availability = FieldProperty([dict(
        week_day=str,
        start_time=dict(h=int, m=int),
        end_time=dict(h=int, m=int))])
    localization = FieldProperty(dict(city=str, country=str))
    timezone = FieldProperty(str)
    sent_user_message_times = FieldProperty([S.DateTime])
    inactiveperiod = FieldProperty([dict(
        start_date=S.DateTime,
        end_date=S.DateTime)])

    # Additional contacts
    socialnetworks = FieldProperty([dict(socialnetwork=str, accounturl=str)])
    telnumbers = FieldProperty([str])
    skypeaccount = FieldProperty(str)
    webpages = FieldProperty([str])

    # Skills list
    skills = FieldProperty([dict(
        category_id=S.ObjectId,
        level=S.OneOf('low', 'high', 'medium'),
        comment=str)])

    # Statistics
    stats_id = FieldProperty(S.ObjectId, if_missing=None)
    last_access = FieldProperty(dict(
        login_date=S.DateTime,
        login_ip=str,
        login_ua=str,
        session_date=S.DateTime,
        session_ip=str,
        session_ua=str))

    def __repr__(self):
        return ('<User username={s.username!r} display_name={s.display_name!r} _id={s._id!r} '
                'disabled={s.disabled!r} pending={s.pending!r}>'.format(s=self))

    def index(self):
        provider = plugin.AuthenticationProvider.get(None)  # no need in request here
        localization = '{}/{}'.format(
            self.get_pref('localization')['country'],
            self.get_pref('localization')['city'])
        socialnetworks = ' '.join(['{}: {}'.format(n['socialnetwork'], n['accounturl'])
                                   for n in self.get_pref('socialnetworks')])
        fields = dict(
            id=self.index_id(),
            title='User %s' % self.username,
            url_s=self.url(),
            type_s=self.type_s,
            username_s=self.username,
            email_addresses_t=' '.join([e for e in self.email_addresses if e]),
            last_password_updated_dt=self.last_password_updated,
            disabled_b=self.disabled,
            pending_b=self.pending,
            results_per_page_i=self.get_pref('results_per_page'),
            email_address_s=self.get_pref('email_address'),
            email_format_s=self.get_pref('email_format'),
            disable_user_messages_b=self.get_pref('disable_user_messages'),
            display_name_t=self.get_pref('display_name'),
            sex_s=self.get_pref('sex'),
            birthdate_dt=self.get_pref('birthdate'),
            localization_s=localization,
            timezone_s=self.get_pref('timezone'),
            socialnetworks_t=socialnetworks,
            telnumbers_t=' '.join([t for t in self.get_pref('telnumbers') if t]),
            skypeaccount_s=self.get_pref('skypeaccount'),
            webpages_t=' '.join([p for p in self.get_pref('webpages') if p]),
            skills_t=' '.join([s['skill'].fullpath for s in self.get_skills() if s.get('skill')]),
            last_access_login_date_dt=self.last_access['login_date'],
            last_access_login_ip_s=self.last_access['login_ip'],
            last_access_login_ua_t=self.last_access['login_ua'],
            last_access_session_date_dt=self.last_access['session_date'],
            last_access_session_ip_s=self.last_access['session_ip'],
            last_access_session_ua_t=self.last_access['session_ua'],
            user_registration_date_dt=self.registration_date(),
        )
        return dict(provider.index_user(self), **fields)

    def track_login(self, req):
        user_ip = utils.ip_address(req)
        user_agent = req.headers.get('User-Agent')
        self.last_access['login_date'] = datetime.utcnow()
        self.last_access['login_ip'] = user_ip
        self.last_access['login_ua'] = user_agent
        session(self).flush(self)

    def track_active(self, req):
        user_ip = utils.ip_address(req)
        user_agent = req.headers.get('User-Agent')
        now = datetime.utcnow()
        last_date = self.last_access['session_date']
        date_changed = last_date is None or last_date.date() != now.date()
        ip_changed = user_ip != self.last_access['session_ip']
        ua_changed = user_agent != self.last_access['session_ua']
        if date_changed or ip_changed or ua_changed:
            self.last_access['session_date'] = datetime.utcnow()
            self.last_access['session_ip'] = user_ip
            self.last_access['session_ua'] = user_agent
            session(self).flush(self)

    def add_login_detail(self, detail):
        try:
            session(detail).flush(detail)
        except DuplicateKeyError:
            session(detail).expunge(detail)

    def backfill_login_details(self, auth_provider):
        # ".*" at start of regex and the DOTALL flag is needed only for the test, which uses mim
        # Fixed in ming f9f69d3c, so once we upgrade to 0.6.1+ we can remove it
        msg_regex = re.compile(r'.*^({})'.format('|'.join([re.escape(line_prefix)
                                                           for line_prefix
                                                           in auth_provider.trusted_auditlog_line_prefixes])),
                               re.MULTILINE | re.DOTALL)
        for auditlog in AuditLog.for_user(self, message=msg_regex):
            if not msg_regex.search(auditlog.message):
                continue
            login_detail = auth_provider.login_details_from_auditlog(auditlog)
            if login_detail:
                self.add_login_detail(login_detail)

    def send_password_reset_email(self, email_address=None, subject_tmpl='{site_name} Password recovery'):
        if email_address is None:
            email_address = self.get_pref('email_address')
        reset_url = self.make_password_reset_url()

        log.info('Sending password recovery link to %s', email_address)
        subject = subject_tmpl.format(site_name=config['site_name'])
        text = g.jinja2_env.get_template('allura:templates/mail/forgot_password.txt').render(dict(
            user=self,
            config=config,
            reset_url=reset_url,
        ))
        allura.tasks.mail_tasks.send_system_mail_to_user(email_address, subject, text)

    def make_password_reset_url(self):
        hash = h.nonce(42)
        self.set_tool_data('AuthPasswordReset',
                           hash=hash,
                           hash_expiry=datetime.utcnow() +
                                       timedelta(seconds=int(config.get('auth.recovery_hash_expiry_period', 600))))
        reset_url = h.absurl(f'/auth/forgotten_password/{hash}')
        return reset_url

    def can_send_user_message(self):
        """Return true if User is permitted to send a mesage to another user.

        Returns False if User has exceeded the user message rate limit, in
        which case another message may not be sent until sufficient time has
        passed to clear the limit.

        """
        now = datetime.utcnow()
        time_interval = timedelta(seconds=g.user_message_time_interval)
        self.sent_user_message_times = [t for t in self.sent_user_message_times
                                        if t + time_interval > now]
        return len(self.sent_user_message_times) < g.user_message_max_messages

    def time_to_next_user_message(self):
        """Return a timedelta of the time remaining before this user can send
        another user message.

        Returns zero if user message can be sent immediately.

        """
        if self.can_send_user_message():
            return 0
        return (self.sent_user_message_times[0] +
                timedelta(seconds=g.user_message_time_interval) -
                datetime.utcnow())

    def send_user_message(self, user, subject, message, cc, reply_to_real_address, sender_email_address):
        """Send a user message (email) to ``user``.

        """
        tmpl = g.jinja2_env.get_template(
            'allura:ext/user_profile/templates/message.html')
        tmpl_context = {
            'message_text': message,
            'site_name': config['site_name'],
            'base_url': config['base_url'],
            'user': c.user,
        }
        real_address = user.preferences.email_address
        reply_to = self.get_pref('email_address')
        if reply_to_real_address:
            reply_to = sender_email_address
        allura.tasks.mail_tasks.sendsimplemail.post(
            toaddr=user.get_pref('email_address'),
            fromaddr=self.get_pref('email_address'),
            reply_to=reply_to,
            message_id=h.gen_message_id(),
            subject=subject,
            text=tmpl.render(tmpl_context),
            cc=cc)
        self.sent_user_message_times.append(datetime.utcnow())

    def send_user_mention_notification(self, mentioned_by, artifact):
        """Send user mention notification to {self} user.

        """
        tmpl = g.jinja2_env.get_template('allura:templates/mail/usermentions_email.md')
        subject = '[{}:{}] Your name was mentioned'.format(
            c.project.shortname, c.app.config.options.mount_point)
        item_url = artifact.url()
        if artifact.type_s == 'Post':
            item_url = artifact.url_paginated()
        tmpl_context = {
            'site_domain': config['domain'],
            'base_url': config['base_url'],
            'user': c.user,
            'artifact_link': h.absurl(item_url),
            'artifact_linktext': artifact.link_text(),
            'mentioned_by': mentioned_by
        }
        allura.tasks.mail_tasks.sendsimplemail.post(
            toaddr=self.get_pref('email_address'),
            fromaddr=g.noreply,
            reply_to=g.noreply,
            message_id=h.gen_message_id(),
            subject=subject,
            text=tmpl.render(tmpl_context))

    @property
    def activity_name(self):
        return self.display_name or self.username

    @property
    def activity_extras(self):
        d = ActivityObject.activity_extras.fget(self)
        d.update(icon_url=self.icon_url())
        return d

    @property
    def stats(self):
        if 'userstats' in g.entry_points['stats']:
            from forgeuserstats.model.stats import UserStats

            if self.stats_id:
                return UserStats.query.get(_id=self.stats_id)
            return UserStats.create(self)
        else:
            return None

    def get_pref(self, pref_name):
        return plugin.UserPreferencesProvider.get().get_pref(self, pref_name)

    def set_pref(self, pref_name, pref_value):
        return plugin.UserPreferencesProvider.get().set_pref(self, pref_name, pref_value)

    def add_multivalue_pref(self, pref_name, pref_data):
        return plugin.UserPreferencesProvider.get().add_multivalue_pref(self, pref_name, pref_data)

    def remove_multivalue_pref(self, pref_name, pref_data):
        return plugin.UserPreferencesProvider.get().remove_multivalue_pref(self, pref_name, pref_data)

    def get_localized_availability(self, tz_name):
        week_day = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                    'Friday', 'Saturday', 'Sunday']
        avail = self.get_availability_timeslots()
        usertimezone = timezone(self.get_pref('timezone') or 'UTC')
        chosentimezone = timezone(tz_name)
        retlist = []
        for t in avail:
            today = datetime.today()
            start = datetime(
                today.year, today.month, today.day,
                t['start_time'].hour, t['start_time'].minute, 0)
            end = datetime(
                today.year, today.month, today.day,
                t['end_time'].hour, t['end_time'].minute, 0)

            loctime1 = usertimezone.localize(start)
            loctime2 = usertimezone.localize(end)
            convtime1 = loctime1.astimezone(chosentimezone)
            convtime2 = loctime2.astimezone(chosentimezone)

            dif_days_start = convtime1.weekday() - today.weekday()
            index = (week_day.index(t['week_day']) + dif_days_start) % 7
            week_day_start = week_day[index]
            week_day_end = week_day[index]

            if week_day_start == week_day_end:
                retlist.append(dict(
                    week_day=week_day_start,
                    start_time=convtime1.time(),
                    end_time=convtime2.time()))
            else:
                retlist.append(dict(
                    week_day=week_day_start,
                    start_time=convtime1.time(),
                    end_time=time(23, 59)))
                retlist.append(dict(
                    week_day=week_day_end,
                    start_time=time(0, 0),
                    end_time=convtime2.time()))

        return sorted(
            retlist,
            key=lambda k: (week_day.index(k['week_day']), k['start_time']))

    def get_skills(self):
        from allura.model.project import TroveCategory

        retval = []
        for el in self.skills:
            d = dict(
                skill=TroveCategory.query.get(_id=el["category_id"]),
                level=el.level,
                comment=el.comment)
            retval.append(d)
        return retval

    def get_availability_timeslots(self):
        retval = []
        for el in self.get_pref('availability'):
            start, end = (el.get('start_time'), el.get('end_time'))
            (starth, startm) = (start.get('h'), start.get('m'))
            (endh, endm) = (end.get('h'), end.get('m'))
            newdict = dict(
                week_day=el.get('week_day'),
                start_time=time(starth, startm, 0),
                end_time=time(endh, endm, 0))
            retval.append(newdict)
        return retval

    def get_inactive_periods(self, include_past_periods=False):
        retval = []
        for el in self.inactiveperiod:
            d1, d2 = (el.get('start_date'), el.get('end_date'))
            newdict = dict(start_date=d1, end_date=d2)
            if include_past_periods or newdict['end_date'] > datetime.today():
                retval.append(newdict)
        return retval

    def url(self):
        '''
        Return the URL (relative to root domain) for this user's user-project.
        This includes any special handling via the :class:`~allura.lib.plugin.AuthenticationProvider` to determine
        the proper user-project name
        '''
        return plugin.AuthenticationProvider.get(request).user_project_url(self)

    @memoize
    def icon_url(self, gravatar_default_url=None, return_more=False):
        icon_url = None
        try:
            private_project = self.private_project()
        except Exception:
            log.warn('Error getting/creating user-project for %s',
                     self.username, exc_info=True)
            private_project = None
        icon_source = None
        if private_project and private_project.icon:
            icon_url = config.get('static.icon_base', '') + self.url() + 'user_icon'
            icon_source = 'local'
        elif self.preferences.email_address and h.asbool(config.get('use_gravatar')):
            gravatar_args = {}
            if gravatar_default_url:
                gravatar_args['d'] = gravatar_default_url
            icon_url = g.gravatar(self.preferences.email_address, **gravatar_args)
            icon_source = 'gravatar'
        elif config.get('default_avatar_image'):
            icon_url = config['default_avatar_image']
            icon_source = 'default'

        if return_more:
            return icon_url, private_project, icon_source
        else:
            return icon_url

    @classmethod
    def upsert(cls, username):
        u = cls.query.get(username=username)
        if u is not None:
            return u
        try:
            u = cls(username=username)
            session(u).flush(u)
        except pymongo.errors.DuplicateKeyError:
            session(u).expunge(u)
            u = cls.query.get(username=username)
        return u

    @classmethod
    def by_email_address(cls, addr, only_confirmed=True):
        q = dict(email=addr)
        if only_confirmed:
            q['confirmed'] = True
        addrs = EmailAddress.find(q)
        users = [ea.claimed_by_user(not only_confirmed) for ea in addrs]
        users = [u for u in users if u is not None]
        if len(users) > 1:
            log.warn('Multiple active users matching confirmed email: %s %s. '
                     'Using first one', [u.username for u in users], addr)
        return users[0] if len(users) > 0 else None

    @classmethod
    def by_username(cls, name):
        if not name:
            return cls.anonymous()
        user = cls.query.get(username=name)
        if user:
            return user
        return plugin.AuthenticationProvider.get(request).by_username(name)

    def get_tool_data(self, tool, key, default=None):
        return self.tool_data.get(tool, {}).get(key, default)

    def set_tool_data(self, tool, **kw):
        d = self.tool_data.setdefault(tool, {})
        d.update(kw)
        state(self).soil()

    def address_object(self, addr):
        return EmailAddress.get(email=addr, claimed_by_user_id=self._id)

    def claim_address(self, email_address):
        addr = EmailAddress.canonical(email_address)
        email_addr = EmailAddress.create(addr)
        if email_addr:
            email_addr.claimed_by_user_id = self._id
            if addr not in self.email_addresses:
                self.email_addresses.append(addr)
            session(email_addr).flush(email_addr)
            return email_addr

    @classmethod
    def register(cls, doc, make_project=True):
        from allura import model as M

        auth_provider = plugin.AuthenticationProvider.get(request)
        user = auth_provider.register_user(doc)
        user.set_pref('mention_notifications', True)
        if user and 'display_name' in doc:
            user.set_pref('display_name', doc['display_name'])
        if user:
            g.statsUpdater.newUser(user)
        if user and make_project:
            n = M.Neighborhood.query.get(name='Users')
            n.register_project(auth_provider.user_project_shortname(user),
                               user=user, user_project=True)
        return user

    @LazyProperty
    def neighborhood(self):
        from allura import model as M

        return M.Neighborhood.query.get(name='Users')

    def private_project(self):
        '''
        Returns the personal user-project for the user
        '''
        if self.disabled or self.pending:
            return None

        from allura import model as M

        n = self.neighborhood
        auth_provider = plugin.AuthenticationProvider.get(request)
        project_shortname = auth_provider.user_project_shortname(self)
        p = M.Project.query.get(
            shortname=project_shortname, neighborhood_id=n._id)
        if p and p.deleted:
            # really delete it, since registering a new project would conflict
            # with the "deleted" one
            log.info(
                'completely deleting user project (was already flagged as deleted) %s',
                project_shortname)
            p.delete()
            ThreadLocalORMSession.flush_all()
            p = None
        if not p and not self.is_anonymous():
            # create user-project on demand if it is missing
            p = n.register_project(
                project_shortname, user=self, user_project=True)
        return p

    @property
    def script_name(self):
        return '/u/' + self.username + '/'

    def my_projects(self) -> typing.Iterable[Project]:
        if self.is_anonymous():
            return []
        roles = g.credentials.user_roles(user_id=self._id)
        # filter out projects to which the user belongs to no named groups (i.e., role['roles'] is empty)
        projects = [r['project_id'] for r in roles if r['roles']]
        from .project import Project

        return Project.query.find({'_id': {'$in': projects}, 'deleted': False}).sort('name', pymongo.ASCENDING)

    def my_projects_by_role_name(self, role_name):
        """
        Return  only projects for which user has
        that role.
        """
        if self.is_anonymous():
            return []
        reaching_role_ids = list(
            g.credentials.user_roles(user_id=self._id).reaching_ids_set)
        reaching_roles = ProjectRole.query.find(
            {'_id': {'$in': reaching_role_ids}, 'name': role_name})
        projects = [r['project_id'] for r in reaching_roles]
        from .project import Project

        return Project.query.find({'_id': {'$in': projects}, 'deleted': False}).all()

    def my_merge_requests(self):
        if self.is_anonymous():
            return

        from .repository import MergeRequest

        return MergeRequest.query.find({'creator_id': self._id}).sort('mod_date', pymongo.DESCENDING)

    def set_password(self, new_password):
        return plugin.AuthenticationProvider.get(request).set_password(
            self, None, new_password)

    @classmethod
    def anonymous(cls):
        anon = cls(
            _id=None,
            username='*anonymous',
            display_name='Anonymous')
        session(anon).expunge(anon)  # don't save this transient Anon record
        return anon

    def __eq__(self, o):
        # maybe could do all _id equal, but not sure.  Just supporting *anonymous user for now
        if self._id is None:
            return isinstance(o, User) and hasattr(o, '_id') and o._id == self._id
        else:
            return super().__eq__(o)

    def __hash__(self):
        # Since we've implemented __eq__ we need to provide a __hash__ implementation
        # https://docs.python.org/3/reference/datamodel.html#object.__hash__
        if self._id is None:
            return 0
        else:
            return super().__hash__()

    def is_anonymous(self):
        return self._id is None or self.username == ''

    def email_address_header(self):
        h = header.Header()
        h.append('"{}"{}'.format(self.get_pref('display_name'), ''))
        h.append('<%s>' % self.get_pref('email_address'))
        return h

    def update_notifications(self):
        return plugin.AuthenticationProvider.get(request).update_notifications(self)

    @classmethod
    def withskill(cls, skill):
        return cls.query.find({"skills.category_id": skill._id})

    def __json__(self):
        return dict(
            username=self.username,
            name=self.display_name,
            url=h.absurl(self.url()),
        )

    def registration_date(self):
        p = plugin.AuthenticationProvider.get(request)
        return p.user_registration_date(self)


class ProjectRole(MappedClass):
    """
    The roles that a single user holds in a project.
    Also the named roles (called "Groups" in the UI) are in this model (and can include other named roles)

    :var user_id: used if this role is for a single user.  Empty for named roles
    :var project_id: the project id
    :var name: named roles (like Admin, Developer, custom-names-too)
    :var roles: a list of other :class:`ProjectRole` ``ObjectId`` values which this user/group has access to
    """

    class __mongometa__:
        session = main_orm_session
        name = 'project_role'
        unique_indexes = [('user_id', 'project_id', 'name')]
        indexes = [
            ('user_id',),
            ('project_id', 'name'),  # used in ProjectRole.by_name()
            ('roles',),
        ]

    query: 'Query[ProjectRole]'

    _id = FieldProperty(S.ObjectId)
    user_id: ObjectId = AlluraUserProperty(if_missing=None)
    project_id = ForeignIdProperty('Project', if_missing=None)
    name = FieldProperty(str)
    roles = FieldProperty([S.ObjectId])

    user = RelationProperty('User')
    project = RelationProperty('Project')

    def __init__(self, **kw):
        assert 'project_id' in kw, 'Project roles must specify a project id'
        super().__init__(**kw)

    def display(self):
        if self.name:
            return self.name
        if self.user_id:
            u = self.user
            if u.username:
                uname = u.username
            elif u.get_pref('display_name'):
                uname = u.get_pref('display_name')
            else:
                uname = u._id
            return '*user-%s' % uname
        return '**unknown name role: %s' % self._id  # pragma no cover

    @classmethod
    def by_user(cls, user, project=None, upsert=False):
        if project is None:
            project = c.project
        if user.is_anonymous():
            return cls.anonymous(project)
        if upsert:
            return cls.upsert(
                user_id=user._id,
                project_id=project.root_project._id,
            )
        else:
            return cls.query.get(
                user_id=user._id,
                project_id=project.root_project._id,
            )

    @classmethod
    def by_name(cls, name, project=None):
        if project is None:
            project = c.project
        if hasattr(project, 'root_project'):
            project = project.root_project
        if hasattr(project, '_id'):
            project_id = project._id
        else:
            project_id = project
        role = cls.query.get(
            name=name,
            project_id=project_id)
        return role

    @classmethod
    def anonymous(cls, project=None):
        return cls.by_name('*anonymous', project)

    @classmethod
    def authenticated(cls, project=None):
        return cls.by_name('*authenticated', project)

    @classmethod
    def upsert(cls, **kw):
        obj = cls.query.get(**kw)
        if obj is not None:
            return obj
        try:
            obj = cls(**kw)
            session(obj).insert_now(obj, state(obj))
        except pymongo.errors.DuplicateKeyError:
            session(obj).expunge(obj)
            obj = cls.query.get(**kw)
        return obj

    @property
    def special(self):
        if self.name:
            return '*' == self.name[0]
        if self.user_id:
            return True
        return False  # pragma no cover

    @property
    def user(self):
        if (self.user_id is None
            and self.name
            and self.name != '*anonymous'):
            return None
        return User.query.get(_id=self.user_id)

    @property
    def settings_href(self):
        if self.name in ('Admin', 'Developer', 'Member'):
            return None
        return self.project.url() + 'admin/groups/' + str(self._id) + '/'

    def parent_roles(self):
        return self.query.find({'roles': self._id}).all()

    def child_roles(self):
        to_check = [] + self.roles
        found_roles = []
        while to_check:
            checking = to_check.pop()
            for role in self.query.find({'_id': checking}).all():
                if role not in found_roles:
                    found_roles.append(role)
                    to_check = to_check + role.roles
        return found_roles

    def users_with_role(self, project=None):
        if not project:
            project = c.project
        return self.query.find(dict(project_id=project._id,
                                    user_id={'$ne': None}, roles=self._id)).all()


class AuditLog(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name = 'audit_log'
        indexes = [
            'project_id',
            'user_id',
        ]

    query: 'Query[AuditLog]'

    _id = FieldProperty(S.ObjectId)
    project_id = ForeignIdProperty('Project', if_missing=None)
    project = RelationProperty('Project')
    user_id: ObjectId = AlluraUserProperty()
    user = RelationProperty('User')
    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)
    url = FieldProperty(str)
    message = FieldProperty(str)

    @property
    def timestamp_str(self):
        return self.timestamp.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def message_html(self):
        standard_metadata_prefixes = (
            'Done by user:',
            'IP Address:',
            'User-Agent:',
        )
        with_br = h.nl2br_jinja_filter(self.message)
        message_bold = '<br>\n'.join([
            line if line.startswith(standard_metadata_prefixes) else f'<strong>{line}</strong>'
            for line in
            with_br.split('<br>\n')
        ])
        return Markup(message_bold)

    @property
    def url_str(self):
        scheme, netloc, path, params, query, fragment = urlparse(self.url)
        s = path
        if params:
            s += ';' + params
        if query:
            s += '?' + query
        if fragment:
            s += '#' + fragment
        return s

    @classmethod
    def log(cls, message, *args, **kwargs):
        project = kwargs.pop('project') if 'project' in kwargs else c.project
        user = kwargs.pop('user', c.user)
        url = kwargs.pop('url', '')
        if not url:
            try:
                url = request.url
            except AttributeError:
                pass
        if args:
            message = message % args
        elif kwargs:
            message = message % kwargs
        pid = project._id if project is not None else None
        if pid is None and user is None or user.is_anonymous():
            return
        return cls(project_id=pid, user_id=user._id, url=url, message=message)

    @classmethod
    def for_user(cls, user, **kwargs):
        return cls.query.find(dict(project_id=None, user_id=user._id, **kwargs))

    @classmethod
    def log_user(cls, message, *args, **kwargs):
        kwargs['project'] = None
        return cls.log(message, *args, **kwargs)

    @classmethod
    def comment_user(cls, by, message, *args, **kwargs):
        message = f'Comment by {by.username}: {message}'
        return cls.log_user(message, *args, **kwargs)


class UserLoginDetails(MappedClass):
    """
    Store unique entries for users' previous login details.

    Used to help determine if new logins are suspicious or not
    """

    class __mongometa__:
        name = 'user_login_details'
        session = main_explicitflush_orm_session
        indexes = ['user_id']
        unique_indexes = [('user_id', 'ip', 'ua'),  # DuplicateKeyError checked in add_login_detail
                          ]

    query: 'Query[UserLoginDetails]'

    _id = FieldProperty(S.ObjectId)
    user_id: ObjectId = AlluraUserProperty(required=True)
    ip = FieldProperty(str)
    ua = FieldProperty(str)
    extra = FieldProperty({
        str: S.Anything
    })

    user = RelationProperty('User')
