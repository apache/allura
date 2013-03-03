import types
import os
import re
import logging
import urllib
import hmac
import hashlib
from urlparse import urlparse
from email import header
from hashlib import sha256
import uuid
from pytz import timezone
from datetime import timedelta, date, datetime, time
from pkg_resources import iter_entry_points

import iso8601
import pymongo
from pylons import tmpl_context as c, app_globals as g
from pylons import request

from ming import schema as S
from ming import Field, collection
from ming.orm import session, state
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty
from ming.orm.declarative import MappedClass
from ming.orm.ormsession import ThreadLocalORMSession
from ming.utils import LazyProperty

import allura.tasks.mail_tasks
from allura.lib import helpers as h
from allura.lib import plugin
from allura.lib.decorators import memoize

from .session import main_orm_session, main_doc_session
from .session import project_orm_session
from .timeline import ActivityNode, ActivityObject

log = logging.getLogger(__name__)

def smart_str(s, encoding='utf-8', strings_only=False, errors='strict'):
    """
    Returns a bytestring version of 's', encoded as specified in 'encoding'.

    If strings_only is True, don't convert (some) non-string-like objects.

    This function was borrowed from Django
    """
    if strings_only and isinstance(s, (types.NoneType, int)):
        return s
    elif not isinstance(s, basestring):
        try:
            return str(s)
        except UnicodeEncodeError:
            if isinstance(s, Exception):
                # An Exception subclass containing non-ASCII data that doesn't
                # know how to print itself properly. We shouldn't raise a
                # further exception.
                return ' '.join([smart_str(arg, encoding, strings_only,
                        errors) for arg in s])
            return unicode(s).encode(encoding, errors)
    elif isinstance(s, unicode):
        r = s.encode(encoding, errors)
        return r
    elif s and encoding != 'utf-8':
        return s.decode('utf-8', errors).encode(encoding, errors)
    else:
        return s

def generate_smart_str(params):
    for (key, value) in params:
        yield smart_str(key), smart_str(value)

def urlencode(params):
    """
    A version of Python's urllib.urlencode() function that can operate on
    unicode strings. The parameters are first case to UTF-8 encoded strings and
    then encoded as per normal.
    """
    return urllib.urlencode([i for i in generate_smart_str(params)])


class ApiAuthMixIn(object):

    def authenticate_request(self, path, params):
        try:
            # Validate timestamp
            timestamp = iso8601.parse_date(params['api_timestamp'])
            timestamp_utc = timestamp.replace(tzinfo=None) - timestamp.utcoffset()
            if abs(datetime.utcnow() - timestamp_utc) > timedelta(minutes=10):
                return False
            # Validate signature
            api_signature = params['api_signature']
            params = sorted((k,v) for k,v in params.iteritems() if k != 'api_signature')
            string_to_sign = path + '?' + urlencode(params)
            digest = hmac.new(self.secret_key, string_to_sign, hashlib.sha256)
            return digest.hexdigest() == api_signature
        except KeyError:
            return False

    def sign_request(self, path, params):
        if hasattr(params, 'items'): params = params.items()
        has_api_key = has_api_timestamp = has_api_signature = False
        for k,v in params:
            if k == 'api_key': has_api_key = True
            if k == 'api_timestamp': has_api_timestamp = True
            if k == 'api_signature': has_api_signature = True
        if not has_api_key:
            params.append(('api_key', self.api_key))
        if not has_api_timestamp:
            params.append(('api_timestamp', datetime.utcnow().isoformat()))
        if not has_api_signature:
            string_to_sign = urllib.quote(path) + '?' + urlencode(sorted(params))
            digest = hmac.new(self.secret_key, string_to_sign, hashlib.sha256)
            params.append(('api_signature', digest.hexdigest()))
        return params

    def get_capability(self, key):
        return None


class ApiToken(MappedClass, ApiAuthMixIn):
    class __mongometa__:
        name='api_token'
        session = main_orm_session
        unique_indexes = [ 'user_id' ]

    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User')
    api_key = FieldProperty(str, if_missing=lambda:str(uuid.uuid4()))
    secret_key = FieldProperty(str, if_missing=h.cryptographic_nonce)

    user = RelationProperty('User')

    @classmethod
    def get(cls, api_key):
        return cls.query.get(api_key=api_key)


class ApiTicket(MappedClass, ApiAuthMixIn):
    class __mongometa__:
        name='api_ticket'
        session = main_orm_session
    PREFIX = 'tck'

    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User')
    api_key = FieldProperty(str, if_missing=lambda: ApiTicket.PREFIX + h.nonce(20))
    secret_key = FieldProperty(str, if_missing=h.cryptographic_nonce)
    expires = FieldProperty(datetime, if_missing=None)
    capabilities = FieldProperty({str:None})
    mod_date = FieldProperty(datetime, if_missing=datetime.utcnow)

    user = RelationProperty('User')

    @classmethod
    def get(cls, api_ticket):
        if not api_ticket.startswith(cls.PREFIX):
            return None
        return cls.query.get(api_key=api_ticket)

    def authenticate_request(self, path, params):
        if self.expires and datetime.utcnow() > self.expires:
            return False
        return ApiAuthMixIn.authenticate_request(self, path, params)

    def get_capability(self, key):
        return self.capabilities.get(key)

class EmailAddress(MappedClass):
    re_format = re.compile('^.* <(.*)>$')
    class __mongometa__:
        name='email_address'
        session = main_orm_session
        indexes = [
            'claimed_by_user_id']

    _id = FieldProperty(str)
    claimed_by_user_id=FieldProperty(S.ObjectId, if_missing=None)
    confirmed = FieldProperty(bool)
    nonce = FieldProperty(str)

    def claimed_by_user(self):
        return User.query.get(_id=self.claimed_by_user_id)

    @classmethod
    def upsert(cls, addr):
        addr = cls.canonical(addr)
        result = cls.query.get(_id=addr)
        if not result:
            result = cls(_id=addr)
        return result

    @classmethod
    def canonical(cls, addr):
        mo = cls.re_format.match(addr)
        if mo:
            addr = mo.group(1)
        if '@' in addr:
            user, domain = addr.split('@')
            return '%s@%s' % (user, domain.lower())
        else:
            return 'nobody@example.com'

    def send_verification_link(self):
        self.nonce = sha256(os.urandom(10)).hexdigest()
        log.info('Sending verification link to %s', self._id)
        text = '''
To verify the email address %s belongs to the user %s,
please visit the following URL:

    %s
''' % (self._id, self.claimed_by_user().username, g.url('/auth/verify_addr', a=self.nonce))
        log.info('Verification email:\n%s', text)
        allura.tasks.mail_tasks.sendmail.post(
            destinations=[self._id],
            fromaddr=self._id,
            reply_to='',
            subject='Email address verification',
            message_id=h.gen_message_id(),
            text=text)

class OpenId(MappedClass):
    class __mongometa__:
        name='openid'
        session = main_orm_session

    _id = FieldProperty(str)
    claimed_by_user_id=FieldProperty(S.ObjectId, if_missing=None)
    display_identifier=FieldProperty(str)

    @classmethod
    def upsert(cls, url, display_identifier):
        result = cls.query.get(_id=url)
        if not result:
            result = cls(
                _id=url,
                display_identifier=display_identifier)
        return result

    def claimed_by_user(self):
        if self.claimed_by_user_id:
            result = User.query.get(_id=self.claimed_by_user_id)
        else: # pragma no cover
            result = User.register(
                dict(username=None, password=None,
                     display_name=self.display_identifier,
                     open_ids=[self._id]),
                make_project=False)
            self.claimed_by_user_id = result._id
        return result

class AuthGlobals(MappedClass):
    class __mongometa__:
        name='auth_globals'
        session = main_orm_session

    _id = FieldProperty(int)
    next_uid = FieldProperty(int, if_missing=10000)

    @classmethod
    def upsert(cls):
        r = cls.query.get()
        if r is not None: return r
        try:
            r = cls(_id=0)
            session(r).flush(r)
            return r
        except pymongo.errors.DuplicateKeyError: # pragma no cover
            session(r).flush(r)
            r = cls.query.get()
            return r

    @classmethod
    def get_next_uid(cls):
        cls.upsert()
        g = cls.query.find_and_modify(
            query={}, update={'$inc':{'next_uid': 1}},
            new=True)
        return g.next_uid


class User(MappedClass, ActivityNode, ActivityObject):
    SALT_LEN=8
    class __mongometa__:
        name='user'
        session = main_orm_session
        indexes = [ 'tool_data.sfx.userid' ]
        unique_indexes = [ 'username' ]

    _id=FieldProperty(S.ObjectId)
    sfx_userid=FieldProperty(S.Deprecated)
    username=FieldProperty(str)
    open_ids=FieldProperty([str])
    email_addresses=FieldProperty([str])
    password=FieldProperty(str)
    projects=FieldProperty(S.Deprecated)
    tool_preferences=FieldProperty({str:{str:None}}) # full mount point: prefs dict
    tool_data = FieldProperty({str:{str:None}}) # entry point: prefs dict
    display_name=FieldProperty(str)
    disabled=FieldProperty(bool, if_missing=False)
    # Don't use directly, use get/set_pref() instead
    preferences=FieldProperty(dict(
            results_per_page=int,
            email_address=str,
            email_format=str))

    #Personal data
    sex=FieldProperty(
        S.OneOf('Male', 'Female', 'Other', 'Unknown',
        if_missing='Unknown'))
    birthdate=FieldProperty(S.DateTime, if_missing=None)

    #Availability information
    availability=FieldProperty([dict(
        week_day=str,
        start_time=dict(h=int, m=int),
        end_time=dict(h=int, m=int))])
    localization=FieldProperty(dict(city=str,country=str))
    timezone=FieldProperty(str)
    inactiveperiod=FieldProperty([dict(
        start_date=S.DateTime,
        end_date=S.DateTime)])

    #Additional contacts
    socialnetworks=FieldProperty([dict(socialnetwork=str,accounturl=str)])
    telnumbers=FieldProperty([str])
    skypeaccount=FieldProperty(str)
    webpages=FieldProperty([str])

    #Skills list
    skills = FieldProperty([dict(
        category_id = S.ObjectId,
        level = S.OneOf('low', 'high', 'medium'),
        comment=str)])

    #Statistics
    stats_id = FieldProperty(S.ObjectId, if_missing=None)

    @property
    def activity_name(self):
        return self.display_name or self.username

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

    def add_socialnetwork(self, socialnetwork, accounturl):
        if socialnetwork == 'Twitter' and not accounturl.startswith('http'):
            accounturl = 'http://twitter.com/%s' % accounturl.replace('@', '')
        self.socialnetworks.append(dict(
            socialnetwork=socialnetwork,
            accounturl=accounturl))

    def remove_socialnetwork(self, socialnetwork, oldurl):
        for el in self.socialnetworks:
            if el.socialnetwork==socialnetwork and el.accounturl==oldurl:
                del self.socialnetworks[self.socialnetworks.index(el)]
                return

    def add_telephonenumber(self, telnumber):
        self.telnumbers.append(telnumber)

    def remove_telephonenumber(self, oldvalue):
        for el in self.telnumbers:
            if el==oldvalue:
                del self.telnumbers[self.telnumbers.index(el)]
                return

    def add_webpage(self, webpage):
        self.webpages.append(webpage)

    def remove_webpage(self, oldvalue):
        for el in self.webpages:
            if el==oldvalue:
                del self.webpages[self.webpages.index(el)]
                return

    def add_timeslot(self, weekday, starttime, endtime):
        self.availability.append(
           dict(week_day=weekday,
                start_time=starttime,
                end_time=endtime))

    def remove_timeslot(self, weekday, starttime, endtime):
        oldel = dict(week_day=weekday, start_time=starttime, end_time=endtime)
        for el in self.availability:
            if el == oldel:
                del self.availability[self.availability.index(el)]
                return

    def add_inactive_period(self, startdate, enddate):
        self.inactiveperiod.append(
           dict(start_date=startdate,
                end_date=enddate))

    def remove_inactive_period(self, startdate, enddate):
        oldel = dict(start_date=startdate, end_date=enddate)
        for el in self.inactiveperiod:
            if el == oldel:
                del self.inactiveperiod[self.inactiveperiod.index(el)]
                return

    def get_localized_availability(self, tz_name):
        week_day = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                    'Friday', 'Saturday', 'Sunday']
        avail = self.get_availability_timeslots()
        usertimezone = timezone(self.get_pref('timezone'))
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
            dif_days_end = convtime2.weekday() - today.weekday()
            index = (week_day.index(t['week_day'])+dif_days_start) % 7
            week_day_start = week_day[index]
            week_day_end = week_day[index]

            if week_day_start == week_day_end:
                retlist.append(dict(
                    week_day = week_day_start,
                    start_time = convtime1.time(),
                    end_time = convtime2.time()))
            else:
                retlist.append(dict(
                    week_day = week_day_start,
                    start_time = convtime1.time(),
                    end_time = time(23, 59)))
                retlist.append(dict(
                    week_day = week_day_end,
                    start_time = time(0, 0),
                    end_time = convtime2.time()))

        return sorted(
            retlist,
            key=lambda k:(week_day.index(k['week_day']), k['start_time']))

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
        for el in self.availability:
            start, end = (el.get('start_time'), el.get('end_time'))
            (starth, startm) = (start.get('h'), start.get('m'))
            (endh, endm) = (end.get('h'), end.get('m'))
            newdict = dict(
                week_day  = el.get('week_day'),
                start_time= time(starth,startm,0),
                end_time  = time(endh,endm,0))
            retval.append(newdict)
        return retval

    def get_inactive_periods(self, include_past_periods=False):
        retval = []
        for el in self.inactiveperiod:
            d1, d2 = (el.get('start_date'), el.get('end_date'))
            newdict = dict(start_date = d1, end_date = d2)
            if include_past_periods or newdict['end_date'] > datetime.today():
                retval.append(newdict)
        return retval

    def url(self):
        return '/%s/' % plugin.AuthenticationProvider.get(request).user_project_shortname(self)

    @memoize
    def icon_url(self):
        icon_url = None
        try:
            private_project = self.private_project()
        except:
            log.warn('Error getting/creating user-project for %s', self.username, exc_info=True)
            private_project = None
        if private_project and private_project.icon:
            icon_url = self.url()+'user_icon'
        elif self.preferences.email_address:
            icon_url = g.gravatar(self.preferences.email_address)
        return icon_url

    @classmethod
    def upsert(cls, username):
        u = cls.query.get(username=username)
        if u is not None: return u
        try:
            u = cls(username=username)
            session(u).flush(u)
        except pymongo.errors.DuplicateKeyError:
            session(u).expunge(u)
            u = cls.query.get(username=username)
        return u

    @classmethod
    def by_email_address(cls, addr):
        ea = EmailAddress.query.get(_id=addr)
        if ea is None: return None
        return ea.claimed_by_user()

    @classmethod
    def by_username(cls, name):
        if not name:
            return cls.anonymous()
        user = cls.query.get(username=name)
        if user:
            return user
        return plugin.AuthenticationProvider.get(request).by_username(name)

    @classmethod
    def by_display_name(cls, name):
        return plugin.UserPreferencesProvider.get().find_by_display_name(name)

    def get_tool_data(self, tool, key, default=None):
        return self.tool_data.get(tool, {}).get(key, None)

    def set_tool_data(self, tool, **kw):
        d = self.tool_data.setdefault(tool, {})
        d.update(kw)
        state(self).soil()

    def address_object(self, addr):
        return EmailAddress.query.get(_id=addr, claimed_by_user_id=self._id)

    def openid_object(self, oid):
        return OpenId.query.get(_id=oid, claimed_by_user_id=self._id)

    def claim_openid(self, oid_url):
        oid_obj = OpenId.upsert(oid_url, self.get_pref('display_name'))
        oid_obj.claimed_by_user_id = self._id
        if oid_url in self.open_ids: return
        self.open_ids.append(oid_url)

    def claim_address(self, email_address):
        addr = EmailAddress.canonical(email_address)
        email_addr = EmailAddress.upsert(addr)
        email_addr.claimed_by_user_id = self._id
        if addr in self.email_addresses: return
        self.email_addresses.append(addr)

    def claim_only_addresses(self, *addresses):
        '''Claims the listed addresses and no others, setting the confirmed
        attribute to True on all.
        '''
        self.email_addresses = [
            EmailAddress.canonical(a) for a in addresses ]
        addresses = set(self.email_addresses)
        for addr in EmailAddress.query.find(
            dict(claimed_by_user_id=self._id)):
            if addr._id in addresses:
                if not addr.confirmed: addr.confirmed = True
                addresses.remove(addr._id)
            else:
                addr.delete()
        for a in addresses:
            addr = EmailAddress.upsert(a)
            addr.claimed_by_user_id = self._id
            addr.confirmed = True

    @classmethod
    def register(cls, doc, make_project=True):
        from allura import model as M
        auth_provider = plugin.AuthenticationProvider.get(request)
        user = auth_provider.register_user(doc)
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
        if self.disabled:
            return None

        from allura import model as M
        n = self.neighborhood
        auth_provider = plugin.AuthenticationProvider.get(request)
        project_shortname = auth_provider.user_project_shortname(self)
        p = M.Project.query.get(shortname=project_shortname, neighborhood_id=n._id)
        if p and p.deleted:
            # really delete it, since registering a new project would conflict with the "deleted" one
            log.info('completely deleting user project (was already flagged as deleted) %s', project_shortname)
            p.delete()
            ThreadLocalORMSession.flush_all()
            p = None
        if not p and self != User.anonymous():
            # create user-project on demand if it is missing
            p = n.register_project(project_shortname, user=self, user_project=True)
        return p

    @property
    def script_name(self):
        return '/u/' + self.username + '/'

    def my_projects(self):
        '''Find the projects for which this user has a named role.'''
        reaching_role_ids = g.credentials.user_roles(user_id=self._id).reaching_ids_set
        reaching_roles = [ ProjectRole.query.get(_id=i) for i in reaching_role_ids ]
        named_roles = [ r for r in reaching_roles
                                if r.name and r.project and not r.project.deleted ]
        seen_project_ids = set()
        for r in named_roles:
            if r.project_id in seen_project_ids: continue
            seen_project_ids.add(r.project_id)
            yield r.project

    def project_role(self, project=None):
        if project is None: project = c.project
        if self._id is None:
            return ProjectRole.anonymous(project)
        else:
            return ProjectRole.upsert(user_id=self._id, project_id=project.root_project._id)

    def set_password(self, new_password):
        return plugin.AuthenticationProvider.get(request).set_password(
            self, self.password, new_password)

    @classmethod
    def anonymous(cls):
        return User.query.get(_id=None)

    def email_address_header(self):
        h = header.Header()
        h.append(u'"%s" ' % self.get_pref('display_name'))
        h.append(u'<%s>' % self.get_pref('email_address'))
        return h

    def update_notifications(self):
        return plugin.AuthenticationProvider.get(request).update_notifications(self)

    @classmethod
    def withskill(cls, skill):
        return cls.query.find({"skills.category_id" : skill._id})

class OldProjectRole(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name='user'
        unique_indexes = [ ('user_id', 'project_id', 'name') ]

class ProjectRole(MappedClass):
    """
    Per-project roles, called "Groups" in the UI.
    This can be a proxy for a single user.  It can also inherit roles.

    :var user_id: used if this role is for a single user
    :var project_id:
    :var name:
    :var roles: a list of other ProjectRole objectids
    """

    class __mongometa__:
        session = main_orm_session
        name='project_role'
        unique_indexes = [ ('user_id', 'project_id', 'name') ]
        indexes = [
            ('user_id',),
            ('project_id',),
            ('roles',)
            ]

    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User', if_missing=None)
    project_id = ForeignIdProperty('Project', if_missing=None)
    name = FieldProperty(str)
    roles = FieldProperty([S.ObjectId])

    user = RelationProperty('User')
    project = RelationProperty('Project')

    def __init__(self, **kw):
        assert 'project_id' in kw, 'Project roles must specify a project id'
        super(ProjectRole, self).__init__(**kw)

    def display(self):
        if self.name: return self.name
        if self.user_id:
            u = self.user
            if u.username: uname = u.username
            elif u.get_pref('display_name'): uname = u.get_pref('display_name')
            else: uname = u._id
            return '*user-%s' % uname
        return '**unknown name role: %s' % self._id # pragma no cover

    @classmethod
    def by_user(cls, user=None, project=None):
        if user is None and project is None:
            return c.user.current_project_role
        if user is None: user = c.user
        if project is None: project = c.project
        pr = cls.query.get(
            user_id=user._id,
            project_id=project.root_project._id)
        if pr is None:
            pr = cls.query.get(
                user_id=user._id,
                project_id={'$exists':False})
        return pr

    @classmethod
    def by_name(cls, name, project=None):
        if project is None: project = c.project
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
        if obj is not None: return obj
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
        return False # pragma no cover

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
        to_check = []+self.roles
        found_roles = []
        while to_check:
            checking = to_check.pop()
            for role in self.query.find({'_id': checking}).all():
                if role not in found_roles:
                    found_roles.append(role)
                    to_check=to_check+role.roles
        return found_roles

    def users_with_role(self, project=None):
        if not project:
            project = c.project
        return self.query.find(dict(project_id=project._id,
            user_id={'$ne': None}, roles=self._id)).all()

audit_log = collection(
    'audit_log', main_doc_session,
    Field('_id', S.ObjectId()),
    Field('project_id', S.ObjectId, if_missing=None,
          index=True),  # main view of audit log queries by project_id
    Field('user_id', S.ObjectId, if_missing=None),
    Field('timestamp', datetime, if_missing=datetime.utcnow),
    Field('url', str),
    Field('message', str))

class AuditLog(object):

    @property
    def timestamp_str(self):
        return self.timestamp.strftime('%Y-%m-%d %H:%M:%S')

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
        project = kwargs.pop('project', c.project)
        user = kwargs.pop('user', c.user)
        url = kwargs.pop('url', request.url)
        if args:
            message = message % args
        elif kwargs:
            message = message % kwargs
        return cls(project_id=project._id, user_id=user._id, url=url, message=message)

main_orm_session.mapper(AuditLog, audit_log, properties=dict(
        project_id=ForeignIdProperty('Project'),
        project=RelationProperty('Project'),
        user_id=ForeignIdProperty('User'),
        user=RelationProperty('User')))
