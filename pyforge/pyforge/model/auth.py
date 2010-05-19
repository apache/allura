import logging
import os
import urllib
import hmac
import hashlib
from datetime import timedelta, datetime
from base64 import b64encode
from random import randint
from hashlib import sha256

import ldap
import iso8601
import pymongo
import pkg_resources
from pylons import c, g, request
from tg import config
from webob import exc

from ming import schema as S
from ming.utils import LazyProperty
from ming.orm.ormsession import ThreadLocalORMSession
from ming.orm import session, state, MappedClass
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty

from pyforge.lib import helpers as h
from .session import ProjectSession
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session

log = logging.getLogger(__name__)

SALT_LENGTH=8

def encode_password(password, salt=None):
    if salt is None:
        salt = ''.join(chr(randint(1, 0x7f))
                       for i in xrange(SALT_LENGTH))
    hashpass = sha256(salt + password.encode('utf-8')).digest()
    return 'sha256' + salt + b64encode(hashpass)

class ApiToken(MappedClass):
    class __mongometa__:
        name='api_token'
        session = main_orm_session

    _id = FieldProperty(S.ObjectId)
    user_id = ForeignIdProperty('User')
    api_key = FieldProperty(str, if_missing=lambda:h.nonce(20))
    secret_key = FieldProperty(str, if_missing=h.cryptographic_nonce)

    user = RelationProperty('User')

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
            string_to_sign = path + '?' + urllib.urlencode(params)
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
            string_to_sign = path + '?' + urllib.urlencode(sorted(params))
            digest = hmac.new(self.secret_key, string_to_sign, hashlib.sha256)
            params.append(('api_signature', digest.hexdigest()))
        return params

class EmailAddress(MappedClass):
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
        user, domain = addr.split('@')
        return '%s@%s' % (user, domain.lower())

    def send_verification_link(self):
        self.nonce = sha256(os.urandom(10)).hexdigest()
        log.info('Would send verification link to %s', self._id)
        text = '''
To verify the email address %s belongs to the user %s,
please visit the following URL:

    %s
''' % (self._id, self.claimed_by_user().username, g.url('/auth/verify_addr', a=self.nonce))
        log.info('Verification email:\n%s', text)
    
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
    sfx_userid=FieldProperty(int)
    username=FieldProperty(str)
    display_name=FieldProperty(str)
    open_ids=FieldProperty([str])
    email_addresses=FieldProperty([str])
    password=FieldProperty(str)
    projects=FieldProperty([S.ObjectId])
    preferences=FieldProperty(dict(
            email_address=str,
            email_format=str))
    tool_preferences=FieldProperty({str:{str:None}}) # full mount point: prefs dict

    def url(self):
        return '/u/' + self.username + '/'

    @classmethod
    def by_email_address(cls, addr):
        ea = EmailAddress.query.get(_id=addr)
        if ea is None: return None
        return ea.claimed_by_user()

    @classmethod
    def by_username(cls, name):
        return AuthenticationProvider.get(request).by_username(name)

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

    @classmethod
    def register(cls, doc, make_project=True):
        from pyforge import model as M
        result = AuthenticationProvider.get(request).register_user(doc)
        if result and make_project:
            n = M.Neighborhood.query.get(name='Users')
            n.register_project('u/' + result.username, result, user_project=True)
        return result

    def private_project(self):
        from .project import Project
        return Project.query.get(shortname='u/%s' % self.username, deleted=False)

    @property
    def script_name(self):
        return '/u/' + self.username + '/'

    def my_projects(self):
        from .project import Project
        for p in self.projects:
            yield Project.query.get(_id=p, deleted=False)

    def role_iter(self):
        yield ProjectRole.query.get(name='*anonymous')
        if self._id:
            yield ProjectRole.query.get(name='*authenticated')
        if self._id:
            pr = self.project_role()
            for role in pr.role_iter():
                yield role

    def project_role(self, project=None):
        if project is None: project = c.project
        with h.push_config(c, project=project, user=self):
            if self._id is None:
                return ProjectRole.query.get(name='*anonymous')
            try:
                obj = ProjectRole(user_id=self._id)
                session(obj).insert_now(obj, state(obj))
                self.projects.append(c.project._id)
                return obj
            except pymongo.errors.DuplicateKeyError:
                session(obj).expunge(obj)
                return ProjectRole.query.get(user_id=self._id)

    def set_password(self, new_password):
        return AuthenticationProvider.get(request).set_password(
            self, self.password, new_password)

    @classmethod
    def anonymous(cls):
        return User.query.get(_id=None)

class ProjectRole(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name='user'
        unique_indexes = [ ('name', 'user_id') ]
    
    _id = FieldProperty(S.ObjectId)
    name = FieldProperty(str)
    user_id = FieldProperty(S.ObjectId, if_missing=None) # if role is a user
    roles = FieldProperty([S.ObjectId])

    def display(self):
        if self.name: return self.name
        if self.user_id:
            u = self.user
            if u.username: uname = u.username
            elif u.display_name: uname = u.display_name
            else: uname = u._id
            return '*user-%s' % uname
        return '**unknown name role: %s' % self._id # pragma no cover

    @property
    def special(self):
        if self.name:
            return '*' == self.name[0]
        if self.user_id:
            return True
        return False # pragma no cover

    @property
    def user(self):
        return User.query.get(_id=self.user_id)

    def users_with_role(self):
        return [pr.user for pr in ProjectRole.query.find({'roles':self._id}).all() if pr.user_id]

    def role_iter(self, visited=None):
        if visited is None: visited = set()
        if self._id not in visited: 
            yield self
            visited.add(self._id)
            for rid in self.roles:
                pr = ProjectRole.query.get(_id=rid)
                if pr is None: continue
                for rr in pr.role_iter(visited):
                    yield rr

class AuthenticationProvider(object):

    def __init__(self, request):
        self.request = request

    @classmethod
    def get(cls, request):
        method = config.get('auth.method', 'local')
        for ep in pkg_resources.iter_entry_points('pyforge.auth', method):
            return ep.load()(request)
        return None

    @LazyProperty
    def session(self):
        return self.request.environ['beaker.session']

    def authenticate_request(self):
        return User.query.get(_id=self.session.get('userid', None))

    def register_user(self, user_doc):
        raise NotImplementedError, 'register_user'

    def _login(self):
        raise NotImplementedError, '_login'

    def login(self, user=None):
        try:
            if user is None: user = self._login()
            self.session['userid'] = user._id
            self.session.save()
            return user
        except exc.HTTPUnauthorized:
            self.logout()
            raise

    def logout(self):
        self.session['userid'] = None
        self.session.save()

    def by_username(self, username):
        raise NotImplementedError, 'by_username'

    def set_password(self, user, old_password, new_password):
        raise NotImplementedError, 'set_password'

class LocalAuthenticationProvider(AuthenticationProvider):

    def register_user(self, user_doc):
        return User(**user_doc)

    def _login(self):
        user = self.by_username(self.request.params['username'])
        if not self._validate_password(user, self.request.params['password']):
            raise exc.HTTPUnauthorized()
        return user

    def _validate_password(self, user, password):
        if user is None: return False
        if not user.password: return False
        salt = str(user.password[6:6+user.SALT_LEN])
        check = encode_password(self.request.params['password'], salt)
        if check != user.password: return False
        return True

    def by_username(self, username):
        return User.query.get(username=username)

    def set_password(self, user, old_password, new_password):
        user.password = encode_password(new_password)

class LdapAuthenticationProvider(AuthenticationProvider):

    def register_user(self, user_doc):
        password = user_doc.pop('password', None)
        result = User(**user_doc)
        dn = 'uid=%s,%s' % (user_doc['username'], config['auth.ldap.suffix'])
        try:
            con = ldap.initialize(config['auth.ldap.server'])
            con.bind_s(config['auth.ldap.admin_dn'],
                       config['auth.ldap.admin_password'])
            ldap_info = dict(
                uid=user_doc['username'],
                displayName=user_doc['display_name'],
                cn=user_doc['display_name'],
                userPassword=password,
                objectClass=['inetOrgPerson'],
                givenName=user_doc['display_name'].split()[0],
                sn=user_doc['display_name'].split()[-1])
            ldap_info = dict((k,v) for k,v in ldap_info.iteritems()
                             if v is not None)
            try:
                con.add_s(dn, ldap_info.items())
            except ldap.ALREADY_EXISTS:
                con.modify_s(dn, [(ldap.MOD_REPLACE, k, v)
                                  for k,v in ldap_info.iteritems()])
            con.unbind_s()
        except:
            raise
        return result

    def by_username(self, username):
        return User.query.get(username=username)

    def set_password(self, user, old_password, new_password):
        try:
            dn = 'uid=%s,%s' % (self.username, config['auth.ldap.suffix'])
            con = ldap.initialize(config['auth.ldap.server'])
            con.bind_s(dn, old_password)
            con.modify_s(dn, [(ldap.MOD_REPLACE, 'userPassword', new_password)])
            con.unbind_s()
        except ldap.INVALID_CREDENTIALS:
            raise exc.HTTPUnauthorized()

    def _login(self):
        user = User.query.get(username=self.request.params['username'])
        if user is None: raise exc.HTTPUnauthorized()
        try:
            dn = 'uid=%s,%s' % (user.username, config['auth.ldap.suffix'])
            con = ldap.initialize(config['auth.ldap.server'])
            con.bind_s(dn, self.request.params['password'])
            con.unbind_s()
        except ldap.INVALID_CREDENTIALS:
            raise exc.HTTPUnauthorized()
        return user

