import types
import os
import re
import logging
import urllib
import hmac
import hashlib
from datetime import timedelta, datetime
from hashlib import sha256

import iso8601
import pymongo
from pylons import c, g, request

from ming import schema as S
from ming.orm.ormsession import ThreadLocalORMSession
from ming.orm import session, state, MappedClass
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty

from allura.lib import helpers as h
from allura.lib import plugin
from .session import ProjectSession
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session

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


class ApiToken(MappedClass):
    class __mongometa__:
        name='api_token'
        session = main_orm_session

    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User')
    api_key = FieldProperty(str, if_missing=lambda:h.nonce(20))
    secret_key = FieldProperty(str, if_missing=h.cryptographic_nonce)
    expires = FieldProperty(datetime, if_missing=None)
    capabilities = FieldProperty({str:str})

    user = RelationProperty('User')

    def authenticate_request(self, path, params):
        try:
            # Validate timestamp
            timestamp = iso8601.parse_date(params['api_timestamp'])
            timestamp_utc = timestamp.replace(tzinfo=None) - timestamp.utcoffset()
            if self.expires and datetime.utcnow() > self.expires:
                return False
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
        if not has_api_key: params.append(('api_key', self.api_key))
        if not has_api_timestamp:
            params.append(('api_timestamp', datetime.utcnow().isoformat()))
        if not has_api_signature:
            string_to_sign = path + '?' + urlencode(sorted(params))
            digest = hmac.new(self.secret_key, string_to_sign, hashlib.sha256)
            params.append(('api_signature', digest.hexdigest()))
        return params

class EmailAddress(MappedClass):
    re_format = re.compile('^.* <(.*)>$')
    class __mongometa__:
        name='email_address'
        session = main_orm_session

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
        user, domain = addr.split('@')
        return '%s@%s' % (user, domain.lower())

    def send_verification_link(self):
        self.nonce = sha256(os.urandom(10)).hexdigest()
        log.info('Sending verification link to %s', self._id)
        text = '''
To verify the email address %s belongs to the user %s,
please visit the following URL:

    %s
''' % (self._id, self.claimed_by_user().username, g.url('/auth/verify_addr', a=self.nonce))
        log.info('Verification email:\n%s', text)
        g.publish('audit', 'forgemail.send_email', {
                'destinations':[self._id],
                'from':self._id,
                'reply_to':'',
                'message_id':'',
                'subject':'Email address verification',
                'text':text})
    
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
            
class User(MappedClass):
    SALT_LEN=8
    class __mongometa__:
        name='user'
        session = main_orm_session
        unique_indexes = [ 'username' ]

    _id=FieldProperty(S.ObjectId)
    sfx_userid=FieldProperty(S.Deprecated)
    username=FieldProperty(str)
    display_name=FieldProperty(str)
    open_ids=FieldProperty([str])
    email_addresses=FieldProperty([str])
    password=FieldProperty(str)
    projects=FieldProperty(S.Deprecated)
    preferences=FieldProperty(dict(
            results_per_page=int,
            email_address=str,
            email_format=str))
    tool_preferences=FieldProperty({str:{str:None}}) # full mount point: prefs dict
    tool_data = FieldProperty({str:{str:None}}) # entry point: prefs dict
    
    def url(self):
        return '/u/' + self.username.replace('_', '-') + '/'

    @classmethod
    def by_email_address(cls, addr):
        ea = EmailAddress.query.get(_id=addr)
        if ea is None: return None
        return ea.claimed_by_user()

    @classmethod
    def by_username(cls, name):
        return plugin.AuthenticationProvider.get(request).by_username(name)

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
        oid_obj = OpenId.upsert(oid_url, self.display_name)
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
        result = plugin.AuthenticationProvider.get(request).register_user(doc)
        if result and make_project:
            n = M.Neighborhood.query.get(name='Users')
            p = n.register_project('u/' + result.username, user=result, user_project=True)
            # Allow for special user-only tools
            p._extra_tool_status = ['user']
        return result

    def private_project(self):
        from .project import Project
        return Project.query.get(shortname='u/%s' % self.username, deleted=False)

    @property
    def script_name(self):
        return '/u/' + self.username + '/'

    def my_projects(self):
        seen_project_ids = set()
        seen_role_ids = set()
        candidates = ProjectRole.query.find(dict(user_id=self._id)).all()
        user_project = 'u/' + self.username
        while candidates:
            r = candidates.pop(0)
            if r._id in seen_role_ids: continue
            seen_role_ids.add(r._id)
            if r.name and r.project_id not in seen_project_ids:
                seen_project_ids.add(r.project_id)
                if r.project.shortname != user_project: 
                    yield r.project
            candidates += ProjectRole.query.find(dict(
                    _id={'$in':r.roles}))

    def role_iter(self):
        anon_role = ProjectRole.anonymous()
        auth_role = ProjectRole.authenticated()
        if anon_role:
            yield anon_role
        if self._id and auth_role:
            yield auth_role
        if self._id:
            pr = self.project_role()
            for role in pr.role_iter():
                yield role

    def project_role(self, project=None):
        if self._id is None:
            return ProjectRole.anonymous(project)
        pr = ProjectRole.by_user(self, project)
        if pr is not None: return pr
        if project is None: project = c.project
        return ProjectRole.upsert(user_id=self._id, project_id=project.root_project._id)

    def set_password(self, new_password):
        return plugin.AuthenticationProvider.get(request).set_password(
            self, self.password, new_password)

    @classmethod
    def anonymous(cls):
        return User.query.get(_id=None)

class OldProjectRole(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name='user'
        unique_indexes = [ ('user_id', 'project_id', 'name') ]

class ProjectRole(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='project_role'
        unique_indexes = [ ('user_id', 'project_id', 'name') ]
        indexes = [
            ('user_id',)
            ]
    
    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User', if_missing=None) # if role is a user
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
            elif u.display_name: uname = u.display_name
            else: uname = u._id
            return '*user-%s' % uname
        return '**unknown name role: %s' % self._id # pragma no cover

    @classmethod
    def by_user(cls, user=None, project=None):
        if user is None: user = c.user
        if project is None: project = c.project
        pr = cls.query.get(
            user_id=user._id,
            project_id={'$in':[project.root_project._id, None]})
        if pr is None:
            pr = cls.query.get(
                user_id=user._id,
                project_id={'$exists':False})
        return pr

    @classmethod
    def by_name(cls, name, project=None):
        if project is None: project = c.project
        role = cls.query.get(
            name=name,
            project_id={'$in':[project.root_project._id, None]})
        if role is None:
            role = cls.query.get(
                name=name,
                project_id={'$exists':False})
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
        if self.user_id is None: return None
        return User.query.get(_id=self.user_id)

    @classmethod
    def roles_reachable_from(cls, *roots):
        to_visit = list(roots)
        visited = set()
        while to_visit:
            pr = to_visit.pop(0)
            if pr in visited: continue
            visited.add(pr)
            yield pr
            to_visit += cls.query.find(dict(_id={'$in':pr.roles})).all()

    @classmethod
    def roles_that_reach(cls, *roots):
        to_visit = list(roots)
        visited = set()
        while to_visit:
            pr = to_visit.pop(0)
            if pr in visited: continue
            visited.add(pr)
            yield pr
            to_visit += cls.query.find(dict(roles=pr._id)).all()

    def users_with_role(self):
        return [
            role.user for role in self.roles_that_reach(self) if role.user_id ]

    def role_iter(self):
        return self.roles_reachable_from(self)

