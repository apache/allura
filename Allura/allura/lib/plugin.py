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

'''
Allura plugins for authentication and project registration
'''
import re
import os
import logging
import subprocess
import string
import crypt
import random
from six.moves.urllib.request import urlopen
from six.moves.urllib.parse import urlparse
from io import BytesIO
from random import randint
from hashlib import sha256
from base64 import b64encode
from datetime import datetime, timedelta
import calendar
import six

try:
    import ldap
    from ldap import modlist
except ImportError:
    ldap = modlist = None
import pkg_resources
import tg
from tg import config, request, redirect, response, flash
from tg import tmpl_context as c, app_globals as g
from webob import exc, Request
from paste.deploy.converters import asbool, asint
from formencode import validators as fev

from ming.utils import LazyProperty
from ming.orm import state
from ming.orm import ThreadLocalORMSession, session, Mapper

from allura.lib import helpers as h
from allura.lib import security
from allura.lib import exceptions as forge_exc
from allura.lib import utils
from allura.tasks import activity_tasks
from allura.tasks.index_tasks import solr_del_project_artifacts

log = logging.getLogger(__name__)


class AuthenticationProvider:

    '''
    An interface to provide authentication services for Allura.

    To use a new provider, expose an entry point in setup.py::

        [allura.auth]
        myprovider = foo.bar:MyAuthProvider

    Then in your .ini file, set ``auth.method=myprovider``
    '''

    forgotten_password_process = False

    pwd_expired_allowed_urls = [
        '/auth/pwd_expired',  # form for changing password, must be first here
        '/auth/pwd_expired_change',
        '/auth/logout',
    ]
    multifactor_allowed_urls = [
        '/auth/multifactor',
        '/auth/do_multifactor',
    ]

    def __init__(self, request):
        self.request = request

    @classmethod
    def get(cls, request):
        '''
        returns the AuthenticationProvider instance for this request
        :rtype: AuthenticationProvider
        '''
        try:
            result = cls._loaded_ep
        except AttributeError:
            method = config.get('auth.method', 'local')
            result = cls._loaded_ep = g.entry_points['auth'][method]
        return result(request)

    @LazyProperty
    def session(self):
        return self.request.environ['beaker.session']

    def authenticate_request(self):
        from allura import model as M
        username = self.session.get('username') or self.session.get('expired-username')
        if username:
            user = M.User.query.get(username=username)  # not .by_username() since that excludes pending/disabled
        else:
            user = None

        if 'multifactor-username' in self.session and request.path not in self.multifactor_allowed_urls:
            # ensure any partially completed multifactor login is not left open, if user goes to any other pages
            del self.session['multifactor-username']
            self.session.save()
        if user is None:
            return M.User.anonymous()
        if user.disabled or user.pending:
            self.logout()
            return M.User.anonymous()
        session_create_date = datetime.utcfromtimestamp(self.session.created)
        if user.is_anonymous():
            sessions_need_reauth = False
        elif self.get_last_password_updated(user) > session_create_date:
            sessions_need_reauth = True
        elif (user.get_tool_data('allura', 'multifactor_date') or datetime.min) > session_create_date:
            sessions_need_reauth = True
        else:
            sessions_need_reauth = False
        if sessions_need_reauth and user.get_tool_data('allura', 'pwd_reset_preserve_session') != self.session.id:
            log.debug('Session logged out: due to user %s pwd change or multifactor enabled', user.username)
            self.logout()
            return M.User.anonymous()

        if self.session.get('pwd-expired') and request.path not in self.pwd_expired_allowed_urls:
            if self.request.environ['REQUEST_METHOD'] == 'GET':
                return_to = self.request.environ['PATH_INFO']
                if self.request.environ.get('QUERY_STRING'):
                    return_to += '?' + self.request.environ['QUERY_STRING']
                location = tg.url(self.pwd_expired_allowed_urls[0], dict(return_to=return_to))
            else:
                # Don't try to re-post; the body has been lost.
                location = tg.url(self.pwd_expired_allowed_urls[0])
            redirect(location)

        return user

    def register_user(self, user_doc):
        '''
        Register a user.

        :param user_doc: a dict with 'username' and 'display_name'.  Optionally 'password' and others
        :rtype: :class:`User <allura.model.auth.User>`
        '''
        raise NotImplementedError('register_user')

    def _login(self):
        '''
        Authorize a user, usually using ``self.request.params['username']`` and ``['password']``

        :rtype: :class:`User <allura.model.auth.User>`
        :raises: HTTPUnauthorized if user not found, or credentials are not valid
        '''
        raise NotImplementedError('_login')

    def after_login(self, user, request):
        '''
        This is a hook so that custom AuthenticationProviders can do things after a successful login.
        '''
        pass

    def login(self, user=None, multifactor_success=False):
        from allura import model as M
        if user is None:
            try:
                user = self._login()  # raises exception if auth fails
            except exc.HTTPUnauthorized:
                h.auditlog_user('Failed login', user=M.User.by_username(self.request.params['username']))
                raise

        if user.get_pref('multifactor') and not multifactor_success:
            self.session['multifactor-username'] = user.username
            h.auditlog_user('Multifactor login - password ok, code not entered yet', user=user)
            self.session.save()
            return None
        else:
            self.session.pop('multifactor-username', None)

        login_details = self.get_login_detail(self.request, user)

        expire_reason = None
        if self.is_password_expired(user):
            h.auditlog_user('Successful login; Password expired', user=user)
            expire_reason = 'via expiration process'
        if not expire_reason and 'password' in self.request.params:
            # password not present with multifactor token; or if login directly after registering is enabled
            expire_reason = self.login_check_password_change_needed(user, self.request.params['password'],
                                                                    login_details)
        if expire_reason:
            self.session['pwd-expired'] = True
            self.session['expired-username'] = user.username
            self.session['expired-reason'] = expire_reason
        else:
            self.session['username'] = user.username
            h.auditlog_user('Successful login', user=user)
        self.after_login(user, self.request)

        if 'rememberme' in self.request.params:
            remember_for = int(config.get('auth.remember_for', 365))
            self.session['login_expires'] = datetime.utcnow() + timedelta(remember_for)
        else:
            self.session['login_expires'] = True
        self.session.save()
        g.statsUpdater.addUserLogin(user)
        user.add_login_detail(login_details)
        user.track_login(self.request)
        return user

    def login_check_password_change_needed(self, user, password, login_details):
        if not self.hibp_password_check_enabled() \
                or not asbool(tg.config.get('auth.hibp_failure_force_pwd_change', False)):
            return

        try:
            security.HIBPClient.check_breached_password(password)
        except security.HIBPClientError as ex:
            log.error("Error invoking HIBP API", exc_info=ex)
        except security.HIBPCompromisedCredentials:
            trusted = False
            try:
                trusted = self.trusted_login_source(user, login_details)
            except Exception:
                log.exception('Error checking if login is trusted: %s %s', user.username, login_details)

            if trusted:
                # current user must change password
                h.auditlog_user('Successful login with password in HIBP breach database, '
                                'from trusted source (reason: {})'.format(trusted), user=user)
                return 'hibp'  # reason
            else:
                # current user may not continue, must reset password via email
                h.auditlog_user('Attempted login from untrusted location with password in HIBP breach database',
                                user=user)
                user.send_password_reset_email(subject_tmpl='Update your {site_name} password')
                raise exc.HTTPBadRequest('To ensure account security, you must reset your password via email.'
                                         '\n'
                                         'Please check your email to continue.')

    def logout(self):
        self.session.invalidate()
        self.session.save()
        response.set_cookie('memorable_forget', '/', secure=request.environ['beaker.session'].secure)

    def validate_password(self, user, password):
        '''Check that provided password matches actual user password

        :rtype: bool
        '''
        raise NotImplementedError('validate_password')

    def disable_user(self, user, **kw):
        '''Disable user account'''
        raise NotImplementedError('disable_user')

    def enable_user(self, user, **kw):
        '''Enable user account'''
        raise NotImplementedError('enable_user')

    def activate_user(self, user, **kw):
        '''Activate user after registration'''
        raise NotImplementedError('activate_user')

    def deactivate_user(self, user, **kw):
        '''Deactivate user (== registation not confirmed)'''
        raise NotImplementedError('deactivate_user')

    def by_username(self, username):
        '''
        Find a user by username.

        :rtype: :class:`User <allura.model.auth.User>` or None
        '''
        raise NotImplementedError('by_username')

    def set_password(self, user, old_password, new_password):
        '''
        Set a user's password.

        A provider implementing this method should store the timestamp of this change, either
        on ``user.last_password_updated`` or somewhere else that a custom ``get_last_password_updated`` method uses.

        :param user: a :class:`User <allura.model.auth.User>`
        :rtype: None
        :raises: HTTPUnauthorized if old_password is not valid
        '''
        raise NotImplementedError('set_password')

    def resend_verification_link(self, user, email):
        '''
        :type user: :class:`allura.model.auth.User`
        :type email: :class:`allura.model.auth.EmailAddress`
        :rtype: None
        '''
        email.send_verification_link()

    def upload_sshkey(self, username, pubkey):
        '''
        Upload an SSH Key.  Providers do not necessarily need to implement this.

        :rtype: None
        :raises: AssertionError with user message, upon any error
        '''
        raise NotImplementedError('upload_sshkey')

    def account_navigation(self):
        return [
            {
                'tabid': 'account_user_prefs',
                'title': 'Preferences',
                'target': "/auth/preferences",
                'alt': 'Manage Personal Preferences',
            },
            {
                'tabid': 'account_user_info',
                'title': 'Personal Info',
                'target': "/auth/user_info",
                'alt': 'Manage Personal Information',
            },
            {
                'tabid': 'account_subscriptions',
                'title': 'Subscriptions',
                'target': "/auth/subscriptions",
                'alt': 'Manage Subscription Preferences',
            },
            {
                'tabid': 'account_oauth',
                'title': 'OAuth',
                'target': "/auth/oauth",
                'alt': 'Manage OAuth Preferences',
            },
        ]

    @LazyProperty
    def account_urls(self):
        return {m['tabid']: m['target'] for m in self.account_navigation()}

    def user_project_shortname(self, user):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :rtype: str
        '''
        raise NotImplementedError('user_project_shortname')

    def user_project_url(self, user):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :rtype: str
        '''
        # default implementation for any providers that haven't implemented this newer method yet
        return f'/{self.user_project_shortname(user)}/'

    def user_by_project_shortname(self, shortname, include_disabled=False):
        '''
        :param str: shortname
        :rtype: user: a :class:`User <allura.model.auth.User>`
        '''
        raise NotImplementedError('user_by_project_shortname')

    def update_notifications(self, user):
        raise NotImplementedError('update_notifications')

    def user_registration_date(self, user):
        '''
        Returns the date in which a user registered himself/herself on the forge.

        :param user: a :class:`User <allura.model.auth.User>`
        :rtype: :class:`datetime <datetime.datetime>`
        '''
        raise NotImplementedError('user_registration_date')

    def get_last_password_updated(self, user):
        '''
        Returns the date when the user updated password for a last time.

        :param user: a :class:`User <allura.model.auth.User>`
        :rtype: :class:`datetime <datetime.datetime>`
        '''
        raise NotImplementedError('get_last_password_updated')

    def get_primary_email_address(self, user_record):
        return user_record.get_pref('email_address') if user_record else None

    def user_details(self, user):
        '''Returns detailed information about user.

        :param user: a :class:`User <allura.model.auth.User>`
        '''
        return {}

    def is_password_expired(self, user):
        days = asint(config.get('auth.pwdexpire.days', 0))
        before = asint(config.get('auth.pwdexpire.before', 0))
        now = datetime.utcnow()
        last_updated = self.get_last_password_updated(user)
        if days and now - last_updated > timedelta(days=days):
            return True
        if before and last_updated < datetime.utcfromtimestamp(before):
            return True
        return False

    def index_user(self, user):
        """Put here additional fields for user index in SOLR."""
        return {}

    def details_links(self, user):
        '''Return list of pairs (url, label) with details
        about the user.
        Links will show up at admin user search page.
        '''
        return [
            ('/nf/admin/user/%s' % user.username, 'Details/Edit'),
        ]

    def hibp_password_check_enabled(self):
        return asbool(tg.config.get('auth.hibp_password_check', False))

    @property
    def trusted_auditlog_line_prefixes(self):
        return [
            "Successful login",  # this is the main one
            # all others are to include login activity before mid-2017 when "Successful login" logs were introduced:
            "Primary email changed",
            "New email address:",
            "Display Name changed",
            "Email address verified:",
            "Password changed",
            "Email address deleted:",
            "Account activated",
            "Phone verification succeeded.",
            "Visited multifactor new TOTP page",
            "Set up multifactor TOTP",
            "Viewed multifactor TOTP config page",
            "Viewed multifactor recovery codes",
            "Regenerated multifactor recovery codes",
        ]

    def login_details_from_auditlog(self, auditlog):
        from allura import model as M
        ip = ua = None
        matches = re.search(r'^IP Address: (.+)\n', auditlog.message, re.MULTILINE)
        if matches:
            ip = matches.group(1)
        matches = re.search(r'^User-Agent: (.+)\n', auditlog.message, re.MULTILINE)
        if matches:
            ua = matches.group(1)
        if ua or ip:
            return M.UserLoginDetails(
                user_id=auditlog.user_id,
                ip=ip,
                ua=ua,
            )

    def get_login_detail(self, request, user):
        from allura import model as M
        return M.UserLoginDetails(
            user_id=user._id,
            ip=utils.ip_address(request),
            ua=request.headers.get('User-Agent'),
        )

    def trusted_login_source(self, user, login_details):
        # TODO: could also factor in User-Agent but hard to know what parts of the UA are meaningful to check here
        from allura import model as M
        for prev_login in M.UserLoginDetails.query.find({'user_id': user._id}):
            if prev_login['ip'] == login_details['ip']:
                return 'exact ip'
            if asbool(tg.config.get('auth.trust_ip_3_octets_match', False)) and \
                    utils.close_ipv4_addrs(prev_login['ip'], login_details['ip']):
                return 'close ip'

        return False

    def username_validator(self, long_message=True):
        validator = fev.Regex(h.re_project_name)
        if long_message:
            validator._messages['invalid'] = (
                'Usernames must include only small letters, numbers, and dashes.'
                ' They must also start with a letter and be at least 3 characters'
                ' long.')
        else:
            validator._messages['invalid'] = 'Usernames only include small letters, numbers, and dashes'
        return validator


class LocalAuthenticationProvider(AuthenticationProvider):

    '''
    Stores user passwords on the User model, in mongo.  Uses per-user salt and
    SHA-256 encryption.
    '''

    forgotten_password_process = True

    def register_user(self, user_doc):
        from allura import model as M
        u = M.User(**user_doc)
        if 'password' in user_doc:
            u.set_password(user_doc['password'])
        if 'reg_date' not in user_doc:
            u.reg_date = datetime.utcnow()
        return u

    def _login(self):
        user = self.by_username(self.request.params['username'])
        if not self._validate_password(user, self.request.params['password']):
            raise exc.HTTPUnauthorized()
        return user

    def disable_user(self, user, **kw):
        user.disabled = True
        session(user).flush(user)
        if kw.get('audit', True):
            h.auditlog_user('Account disabled', user=user)

    def enable_user(self, user, **kw):
        user.disabled = False
        session(user).flush(user)
        if kw.get('audit', True):
            h.auditlog_user('Account enabled', user=user)

    def activate_user(self, user, **kw):
        user.pending = False
        session(user).flush(user)
        if kw.get('audit', True):
            h.auditlog_user('Account activated', user=user)

    def deactivate_user(self, user, **kw):
        user.pending = True
        session(user).flush(user)
        if kw.get('audit', True):
            h.auditlog_user('Account changed to pending', user=user)

    def validate_password(self, user, password):
        return self._validate_password(user, password)

    def _validate_password(self, user, password):
        if user is None:
            return False
        if not user.password:
            return False
        salt = str(user.password[6:6 + user.SALT_LEN])
        check = self._encode_password(password, salt)
        if check != user.password:
            return False
        return True

    def by_username(self, username):
        from allura import model as M
        un = re.escape(username)
        escaped_underscore = re.escape('_')  # changes in py3.x versions # https://docs.python.org/3/library/re.html#re.escape
        un = un.replace(escaped_underscore, '[-_]')
        un = un.replace(r'\-', '[-_]')
        rex = re.compile('^' + un + '$')
        return M.User.query.get(username=rex, disabled=False, pending=False)

    def set_password(self, user, old_password, new_password):
        if old_password is not None and not self.validate_password(user, old_password):
            raise exc.HTTPUnauthorized()
        else:
            user.password = self._encode_password(new_password)
            user.last_password_updated = datetime.utcnow()
            session(user).flush(user)

    def _encode_password(self, password, salt=None):
        from allura import model as M
        if salt is None:
            salt = ''.join(chr(randint(1, 0x7f))
                           for i in range(M.User.SALT_LEN))
        hashpass = sha256((salt + password).encode('utf-8')).digest()
        return 'sha256' + salt + six.ensure_text(b64encode(hashpass))

    def user_project_shortname(self, user):
        # "_" isn't valid for subdomains (which project names are used with)
        # so if a username has a "_" we change it to "-"
        # may need to handle other characters at some point
        return 'u/' + user.username.replace('_', '-')

    def user_project_url(self, user):
        # in contrast with above user_project_shortname()
        # we allow the URL of a user-project to match the username exactly, even if user-project's name is different
        # (nbhd_lookup_first_path will figure it out)
        return f'/u/{user.username}/'

    def user_by_project_shortname(self, shortname, include_disabled=False):
        from allura import model as M
        filters = {
            'pending': False,
        }
        if not include_disabled:
            filters['disabled'] = False
        user = M.User.query.get(username=shortname, **filters)
        if not user and '-' in shortname:
            # try alternate version in case username & user-project shortname differ - see user_project_shortname()
            user = M.User.query.get(username=shortname.replace('-', '_'), **filters)
        return user

    def update_notifications(self, user):
        return ''

    def user_registration_date(self, user):
        if user.reg_date:
            return user.reg_date
        if user._id:
            d = user._id.generation_time
            # generation_time returns tz-aware datetime (in UTC) but we're using naive UTC time everywhere
            return datetime.utcfromtimestamp(calendar.timegm(d.utctimetuple()))
        return datetime.utcnow()

    def get_last_password_updated(self, user):
        d = user.last_password_updated
        if d is None:
            d = self.user_registration_date(user)
        return d


def ldap_conn(who=None, cred=None):
    '''
    Init & bind a connection with the given creds, or the admin creds if not
    specified. Remember to unbind the connection when done.
    '''
    con = ldap.initialize(config['auth.ldap.server'])
    con.simple_bind_s(who or config['auth.ldap.admin_dn'],
                      cred or config['auth.ldap.admin_password'])
    return con


def ldap_user_dn(username):
    'return a Distinguished Name for a given username'
    if not username:
        raise ValueError('Empty username')
    return 'uid={},{}'.format(
        ldap.dn.escape_dn_chars(username),
        config['auth.ldap.suffix'])


class LdapAuthenticationProvider(AuthenticationProvider):

    forgotten_password_process = True

    def register_user(self, user_doc):
        from allura import model as M
        result = M.User(**user_doc)
        if asbool(config.get('auth.ldap.autoregister', True)):
            if asbool(config.get('auth.allow_user_registration', True)):
                raise Exception('You should not have both "auth.ldap.autoregister" and '
                                '"auth.allow_user_registration" set to true')
            else:
                log.debug('LdapAuth: autoregister is true, so only creating the mongo '
                          'record (not creating ldap record)')
                return result

        # full registration into LDAP
        uid = str(M.AuthGlobals.get_next_uid()).encode('utf-8')
        con = ldap_conn()
        uname = user_doc['username'].encode('utf-8')
        display_name = user_doc['display_name'].encode('utf-8')
        ldif_u = modlist.addModlist(dict(
            uid=uname,
            userPassword=self._encode_password(user_doc['password']),
            objectClass=[b'account', b'posixAccount'],
            cn=display_name,
            uidNumber=uid,
            gidNumber=b'10001',
            homeDirectory=b'/home/' + uname,
            loginShell=b'/bin/bash',
            gecos=uname,
            description=b'SCM user account'))
        try:
            con.add_s(ldap_user_dn(user_doc['username']), ldif_u)
        except ldap.ALREADY_EXISTS:
            log.exception('Trying to create existing user %s', uname)
            raise
        con.unbind_s()

        if asbool(config.get('auth.ldap.use_schroot', True)):
            argv = ('schroot -d / -c {} -u root /ldap-userconfig.py init {}'.format(
                config['auth.ldap.schroot_name'], user_doc['username'])).split()
            p = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            rc = p.wait()
            if rc != 0:
                log.error('Error creating home directory for %s',
                          user_doc['username'])
        return result

    def upload_sshkey(self, username, pubkey):
        if not asbool(config.get('auth.ldap.use_schroot', True)):
            raise NotImplementedError('SSH keys are not supported')

        argv = ('schroot -d / -c {} -u root /ldap-userconfig.py upload {}'.format(
            config['auth.ldap.schroot_name'], username)).split() + [pubkey]
        p = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        rc = p.wait()
        if rc != 0:
            errmsg = p.stdout.read()
            log.exception('Error uploading public SSH key for %s: %s',
                          username, errmsg)
            raise AssertionError(errmsg)

    def _get_salt(self, length):
        def random_char():
            return random.choice(string.ascii_uppercase + string.digits)
        return ''.join(random_char() for i in range(length))

    def _encode_password(self, password, salt=None):
        cfg_prefix = 'auth.ldap.password.'
        salt_len = asint(config.get(cfg_prefix + 'salt_len', 16))
        algorithm = config.get(cfg_prefix + 'algorithm', 6)
        rounds = asint(config.get(cfg_prefix + 'rounds', 6000))
        salt = self._get_salt(salt_len) if salt is None else salt
        encrypted = crypt.crypt(
            six.ensure_str(password),
            f'${algorithm}$rounds={rounds}${salt}')
        return b'{CRYPT}%s' % encrypted.encode('utf-8')

    def by_username(self, username):
        from allura import model as M
        return M.User.query.get(username=username, disabled=False, pending=False)

    def set_password(self, user, old_password, new_password):
        dn = ldap_user_dn(user.username)
        if old_password:
            ldap_ident = dn
            ldap_pass = old_password.encode('utf-8')
        else:
            ldap_ident = ldap_pass = None
        try:
            con = ldap_conn(ldap_ident, ldap_pass)
            new_password = self._encode_password(new_password)
            con.modify_s(
                dn, [(ldap.MOD_REPLACE, 'userPassword', new_password)])
            con.unbind_s()
            user.last_password_updated = datetime.utcnow()
            session(user).flush(user)
        except ldap.INVALID_CREDENTIALS:
            raise exc.HTTPUnauthorized()

    def _login(self):
        if ldap is None:
            raise Exception('The python-ldap package needs to be installed.  '
                            'Run `pip install python-ldap` in your allura environment.')
        from allura import model as M
        try:
            username = str(self.request.params['username'])
        except UnicodeEncodeError:
            raise exc.HTTPBadRequest('Unicode is not allowed in usernames')
        if not self._validate_password(username, self.request.params['password']):
            raise exc.HTTPUnauthorized()
        user = M.User.query.get(username=username)
        if user is None:
            if asbool(config.get('auth.ldap.autoregister', True)):
                log.debug('LdapAuth: authorized user {} needs a mongo record registered.  '
                          'Creating...'.format(username))
                user = M.User.register({'username': username,
                                        'display_name': LdapUserPreferencesProvider()._get_pref(username,
                                                                                                'display_name'),
                                        })
            else:
                log.debug(f'LdapAuth: no user {username} found in local mongo')
                raise exc.HTTPUnauthorized()
        elif user.disabled or user.pending:
            log.debug(f'LdapAuth: user {username} is disabled or pending in Allura')
            raise exc.HTTPUnauthorized()
        return user

    def validate_password(self, user, password):
        '''by user'''
        return self._validate_password(user.username, password)

    def _validate_password(self, username, password):
        '''by username'''
        password = h.really_unicode(password).encode('utf-8')
        try:
            ldap_user = ldap_user_dn(username)
        except ValueError:
            return False
        try:
            con = ldap_conn(ldap_user, password)
            con.unbind_s()
            return True
        except (ldap.INVALID_CREDENTIALS, ldap.UNWILLING_TO_PERFORM, ldap.NO_SUCH_OBJECT):
            log.debug(f'LdapAuth: could not authenticate {username}', exc_info=True)
        return False

    def user_project_shortname(self, user):
        return LocalAuthenticationProvider(None).user_project_shortname(user)

    def user_by_project_shortname(self, shortname, **kwargs):
        return LocalAuthenticationProvider(None).user_by_project_shortname(shortname, **kwargs)

    def user_registration_date(self, user):
        # could read this from an LDAP field?
        return LocalAuthenticationProvider(None).user_registration_date(user)

    def update_notifications(self, user):
        return LocalAuthenticationProvider(None).update_notifications(user)

    def disable_user(self, user, **kw):
        return LocalAuthenticationProvider(None).disable_user(user, **kw)

    def enable_user(self, user, **kw):
        return LocalAuthenticationProvider(None).enable_user(user, **kw)

    def activate_user(self, user, **kw):
        return LocalAuthenticationProvider(None).activate_user(user, **kw)

    def deactivate_user(self, user, **kw):
        return LocalAuthenticationProvider(None).deactivate_user(user, **kw)

    def get_last_password_updated(self, user):
        return LocalAuthenticationProvider(None).get_last_password_updated(user)

    def recover_password(self, user):
        return super().recover_password(user)


class ProjectRegistrationProvider:
    '''
    Project registration services for Allura.  This is a full implementation
    and the default.  Extend this class with your own if you need to add more
    functionality.

    To use a new provider, expose an entry point in setup.py::

        [allura.project_registration]
        myprovider = foo.bar:MyAuthProvider

    Then in your .ini file, set registration.method=myprovider

    The provider should expose an attribute, `shortname_validator` which is
    an instance of a FormEncode validator that validates project shortnames.
    The `to_python()` method of the validator should accept a `check_allowed`
    argument to indicate whether additional checks beyond correctness of the
    name should be done, such as whether the name is already in use.
    '''

    def __init__(self):
        from allura.lib.widgets import forms
        self.add_project_widget = forms.NeighborhoodAddProjectForm
        self.shortname_validator = forms.NeighborhoodProjectShortNameValidator(
        )

    @classmethod
    def get(cls):
        '''
        :rtype: ProjectRegistrationProvider
        '''
        from allura.lib import app_globals
        method = config.get('registration.method', 'local')
        return app_globals.Globals().entry_points['registration'][method]()

    def rate_limit(self, user, neighborhood):
        """Check the various config-defined project registration rate
        limits, and if any are exceeded, raise ProjectRatelimitError.

        """
        if security.has_access(neighborhood, 'admin', user=user)():
            return
        opt = 'project.rate_limits'
        project_count = len(list(user.my_projects()))
        # have to have the replace because, the generation_time is offset-aware
        # UTC and h.rate_limit uses offset-naive UTC dates
        start_date = user._id.generation_time.replace(tzinfo=None)
        e = forge_exc.ProjectRatelimitError
        h.rate_limit(opt, project_count, start_date, exception=e)

    def phone_verified(self, user, neighborhood):
        """
        Check if user has completed phone verification.

        Returns True if one of the following is true:
            - phone verification is disabled
            - :param user: has 'admin' access to :param neighborhood:
            - :param user: is has 'admin' access for some project, which belongs to :param neighborhood:
            - phone is already verified for a :param user:

        Otherwise returns False.
        """
        if not asbool(config.get('project.verify_phone')):
            return True
        if security.has_access(neighborhood, 'admin', user=user)():
            return True
        admin_in = [p for p in user.my_projects_by_role_name('Admin')
                    if p.neighborhood_id == neighborhood._id]
        if len(admin_in) > 0:
            return True
        return bool(user.get_tool_data('phone_verification', 'number_hash'))

    def verify_phone(self, user, number, allow_reuse=False):
        from allura import model as M
        ok = {'status': 'ok'}
        if not asbool(config.get('project.verify_phone')):
            return ok
        number = utils.clean_phone_number(number)
        number_hash = utils.phone_number_hash(number)
        if not allow_reuse and M.User.query.find({'tool_data.phone_verification.number_hash': number_hash}).count():
            return {'status': 'error',
                    'error': 'That phone number has already been used.'}
        count = user.get_tool_data('phone_verification', 'count') or 0
        attempt_limit = config.get('phone.attempts_limit', '5')
        if count >= int(attempt_limit):
            msg = 'Maximum phone verification attempts reached.'
            h.auditlog_user(msg, user=user)
            return {'status': 'error',
                    'error': msg
                    }
        user.set_tool_data('phone_verification', count=count + 1)
        log.info('PhoneService going to send a verification for: %s', user.username)
        return g.phone_service.verify(number)

    def check_phone_verification(self, user, request_id, pin, number_hash):
        ok = {'status': 'ok'}
        if not asbool(config.get('project.verify_phone')):
            return ok
        res = g.phone_service.check(request_id, pin)
        if res.get('status') == 'ok':
            user.set_tool_data('phone_verification', number_hash=number_hash)
            msg = f'Phone verification succeeded. Hash: {number_hash}'
            h.auditlog_user(msg, user=user)
        else:
            msg = f'Phone verification failed. Hash: {number_hash}'
            h.auditlog_user(msg, user=user)
        return res

    def register_neighborhood_project(self, neighborhood, users, allow_register=False):
        from allura import model as M
        shortname = '--init--'
        name = 'Home Project for %s' % neighborhood.name
        p = M.Project(neighborhood_id=neighborhood._id,
                      shortname=shortname,
                      name=name,
                      short_description='',
                      description='You can edit this description in the admin page',
                      homepage_title='# ' + name,
                      last_updated=datetime.utcnow(),
                      is_nbhd_project=True,
                      is_root=True)
        try:
            p.configure_project(
                users=users,
                is_user_project=False,
                apps=[
                    ('Wiki', 'wiki', 'Wiki'),
                    ('admin', 'admin', 'Admin')])
        except Exception:
            ThreadLocalORMSession.close_all()
            log.exception('Error registering project %s' % p)
            raise
        if allow_register:
            role_auth = M.ProjectRole.authenticated(p)
            security.simple_grant(p.acl, role_auth._id, 'register')
            state(p).soil()
        return p

    def register_project(self, neighborhood, shortname, project_name, user, user_project, private_project, apps=None,
                         omit_event=False, **kwargs):
        '''Register a new project in the neighborhood.  The given user will
        become the project's superuser.
        '''
        self.validate_project(neighborhood, shortname,
                              project_name, user, user_project, private_project)
        return self._create_project(neighborhood, shortname, project_name, user, user_project, private_project, apps,
                                    omit_event=omit_event)

    def validate_project(self, neighborhood, shortname, project_name, user, user_project, private_project):
        '''
        Validate that a project can be registered, before it is
        '''
        from allura import model as M

        # Check for private project rights
        if neighborhood.features['private_projects'] is False and private_project:
            raise forge_exc.ForgeError(
                "You can't create private projects in the %s neighborhood" %
                neighborhood.name)

        # Check for project limit creation
        nb_max_projects = neighborhood.get_max_projects()
        if nb_max_projects is not None:
            count = M.Project.query.find(dict(
                neighborhood_id=neighborhood._id,
                deleted=False,
                is_nbhd_project=False,
            )).count()
            if count >= nb_max_projects:
                log.exception('Error registering project %s' % project_name)
                raise forge_exc.ProjectOverlimitError()

        self.rate_limit(user, neighborhood)

        if not self.phone_verified(user, neighborhood) and not user_project:
            raise forge_exc.ProjectPhoneVerificationError()

        if user_project and shortname.startswith('u/'):
            check_shortname = shortname.replace('u/', '', 1)
        else:
            check_shortname = shortname
        self.shortname_validator.to_python(check_shortname, neighborhood=neighborhood)

        p = M.Project.query.get(shortname=shortname, neighborhood_id=neighborhood._id)
        if p:
            raise forge_exc.ProjectConflict(
                f'{shortname} already exists in nbhd {neighborhood._id}')

    def index_project(self, project):
        """
        Put here additional fields given project should be indexed by SOLR.
        """
        return dict()

    def _create_project(self, neighborhood, shortname, project_name, user, user_project, private_project, apps,
                        omit_event=False):
        '''
        Actually create the project, no validation.  This should not be called directly
        under normal circumstances.
        '''
        from allura import model as M

        project_template = neighborhood.get_project_template()
        p = M.Project(neighborhood_id=neighborhood._id,
                      shortname=shortname,
                      name=project_name,
                      short_description='',
                      description='You can edit this description in the admin page',
                      homepage_title=shortname,
                      last_updated=datetime.utcnow(),
                      is_nbhd_project=False,
                      is_root=True)
        p.configure_project(
            users=[user],
            is_user_project=user_project,
            is_private_project=private_project or project_template.get(
                'private', False),
            apps=apps or [] if 'tools' in project_template else None)

        M.AuditLog(project_id=p._id, user_id=user._id, message='Project Created!',
                   url=neighborhood.url_prefix + 'add_project')

        # Setup defaults from neighborhood project template if applicable
        offset = p.next_mount_point(include_hidden=True)
        if 'groups' in project_template:
            for obj in project_template['groups']:
                name = obj.get('name')
                permissions = set(obj.get('permissions', [])) & \
                    set(p.permissions)
                usernames = obj.get('usernames', [])
                # Must provide a group name
                if not name:
                    continue
                # If the group already exists, we'll add users to it,
                # but we won't change permissions on the group
                group = M.ProjectRole.by_name(name, project=p)
                if not group:
                    # If creating a new group, *must* specify permissions
                    if not permissions:
                        continue
                    group = M.ProjectRole(project_id=p._id, name=name)
                    p.acl += [M.ACE.allow(group._id, perm)
                              for perm in permissions]
                for username in usernames:
                    guser = M.User.by_username(username)
                    if not (guser and guser._id):
                        continue
                    pr = M.ProjectRole.by_user(guser, project=p, upsert=True)
                    if group._id not in pr.roles:
                        pr.roles.append(group._id)
        if 'tools' in project_template:
            for i, tool in enumerate(project_template['tools'].keys()):
                tool_config = project_template['tools'][tool]
                tool_options = tool_config.get('options', {})
                for k, v in tool_options.items():
                    if isinstance(v, str):
                        tool_options[k] = \
                            string.Template(v).safe_substitute(
                                p.__dict__.get('root_project', {}))
                if p.app_instance(tool) is None:
                    app = p.install_app(tool,
                                        mount_label=tool_config['label'],
                                        mount_point=tool_config['mount_point'],
                                        ordinal=i + offset,
                                        **tool_options)
                    if tool == 'wiki':
                        from forgewiki import model as WM
                        text = tool_config.get('home_text',
                                               '[[members limit=20]]\n[[download_button]]')
                        WM.Page.query.get(
                            app_config_id=app.config._id).text = text

        if 'tool_order' in project_template:
            for i, tool in enumerate(project_template['tool_order']):
                p.app_config(tool).options.ordinal = i
        if 'labels' in project_template:
            p.labels = project_template['labels']
        if 'trove_cats' in project_template:
            for trove_type in project_template['trove_cats'].keys():
                troves = getattr(p, 'trove_%s' % trove_type)
                for trove_id in project_template['trove_cats'][trove_type]:
                    troves.append(
                        M.TroveCategory.query.get(trove_cat_id=trove_id)._id)
        if 'icon' in project_template:
            icon_file = BytesIO(urlopen(project_template['icon']['url']).read())
            p.save_icon(project_template['icon']['filename'], icon_file)

        if user_project:
            # Allow for special user-only tools
            p._extra_tool_status = ['user']
            if p.app_config_by_tool_type('wiki'):
                # add user project informative text to home
                from forgewiki import model as WM
                home_app = p.app_instance('wiki')
                home_page = WM.Page.query.get(app_config_id=home_app.config._id)
                home_page.text = ("This is the personal project of %s."
                                  " This project is created automatically during user registration"
                                  " as an easy place to store personal data that doesn't need its own"
                                  " project such as cloned repositories.") % user.display_name

        # clear the RoleCache for the user so this project will
        # be picked up by user.my_projects()
        g.credentials.clear_user(user._id, None)  # unnamed roles for this user
        # named roles for this project + user
        g.credentials.clear_user(user._id, p._id)
        with h.push_config(c, project=p, user=user):
            ThreadLocalORMSession.flush_all()
            # have to add user to context, since this may occur inside auth code
            # for user-project reg, and c.user isn't set yet
            if not omit_event:
                g.post_event('project_created')
        return p

    def register_subproject(self, project, name, user, install_apps, project_name=None):
        from allura import model as M
        assert h.re_project_name.match(name), 'Invalid subproject shortname'
        shortname = project.shortname + '/' + name
        ordinal = int(project.ordered_mounts(include_hidden=True)
                      [-1]['ordinal']) + 1
        sp = M.Project(
            parent_id=project._id,
            neighborhood_id=project.neighborhood_id,
            shortname=shortname,
            name=project_name or name,
            last_updated=datetime.utcnow(),
            is_root=False,
            ordinal=ordinal,
        )
        with h.push_config(c, project=sp):
            M.AppConfig.query.remove(dict(project_id=c.project._id))
            if install_apps:
                sp.install_app('admin', 'admin', ordinal=1)
                sp.install_app('search', 'search', ordinal=2)
            g.post_event('project_created')
        return sp

    def delete_project(self, project, user):
        for sp in project.subprojects:
            self.delete_project(sp, user)
        project.deleted = True

    def undelete_project(self, project, user):
        project.deleted = False
        for sp in project.subprojects:
            self.undelete_project(sp, user)

    def purge_project(self, project, disable_users=False, reason=None):
        from allura.model import AppConfig
        pid = project._id
        solr_del_project_artifacts.post(pid)
        if disable_users:
            # Disable users if necessary BEFORE removing all project-related documents
            log.info("Disabling users because we're purging project %s", project.url())
            self.disable_project_users(project, reason)
        app_config_ids = [ac._id for ac in AppConfig.query.find(dict(project_id=pid))]
        for m in Mapper.all_mappers():
            mcls = m.mapped_class
            if 'project_id' in m.property_index:
                # Purge the things directly related to the project
                mcls.query.remove(dict(project_id=pid))
            elif 'app_config_id' in m.property_index:
                # ... and the things related to its apps
                mcls.query.remove(dict(app_config_id={'$in': app_config_ids}))
        project.delete()
        session(project).flush()
        g.post_event('project_deleted', project_id=pid, reason=reason)

    def disable_project_users(self, project, reason=None):
        provider = AuthenticationProvider.get(Request.blank('/'))
        users = project.admins() + project.users_with_role('Developer')
        for user in users:
            if user.disabled:
                log.info('User %s is already disabled', user.username)
                continue
            provider.disable_user(user, audit=False)
            msg = 'Account disabled because project {}{} is deleted. Reason: {}'.format(
                project.neighborhood.url_prefix,
                project.shortname,
                reason)
            auditlog = h.auditlog_user(msg, user=user)
            if auditlog:
                session(auditlog).flush(auditlog)
            else:
                log.error('For some reason no auditlog written in disable_project_users for: %s %s', user, msg)
            # `users` can contain duplicates. Make sure changes are visible
            # to next iterations, so that `user.disabled` check works.
            session(user).expunge(user)

    def best_download_url(self, project):
        '''This is the url needed to render a download button.
           It should be overridden for your specific envirnoment'''
        return None

    def registration_date(self, project) -> datetime:
        '''
        Return the datetime the project was created.
        '''
        # generation_time is offset-aware UTC, but everything else is offset-naive
        return project._id.generation_time.replace(tzinfo=None)

    def details_links(self, project):
        '''Return list of pairs (url, label) with details
        about the project.
        Links will show up at admin project search page
        '''
        return [
            (project.url() + 'admin/groups/', 'Members'),
            (project.url() + 'admin/audit/', 'Audit Trail'),
        ]

    def project_from_url(self, url):
        '''Returns a tuple (project, error).

        Where project is the Project instane parsed from url or None if project
        can't be parsed. In that case error will be a string describing the error.
        '''
        from allura.model import Project, Neighborhood
        if url is None:
            return None, 'Empty url'
        url = urlparse(url)
        url = [u for u in url.path.split('/') if u]
        if len(url) == 0:
            return None, 'Empty url'
        if len(url) == 1:
            q = Project.query.find(dict(shortname=url[0]))
            cnt = q.count()
            if cnt == 0:
                return None, 'Project not found'
            if cnt == 1:
                return q.first(), None
            return None, f'Too many matches for project: {cnt}'
        n = Neighborhood.query.get(url_prefix=f'/{url[0]}/')
        if not n:
            return None, 'Neighborhood not found'
        p = Project.query.get(neighborhood_id=n._id, shortname=n.shortname_prefix + url[1])
        if len(url) > 2:
            # Maybe subproject
            subp = Project.query.get(neighborhood_id=n._id, shortname='{}/{}'.format(*url[1:3]))
            if subp:
                return (subp, None)
        return (p, 'Project not found' if p is None else None)


class ThemeProvider:

    '''
    Theme information for Allura.  This is a full implementation
    and the default.  Extend this class with your own if you need to add more
    functionality.

    To use a new provider, expose an entry point in setup.py::

        [allura.theme]
        myprovider = foo.bar:MyThemeProvider

    Then in your .ini file, set theme=mytheme

    The variables referencing jinja template files can be changed to point at your
    own jinja templates.  Use the standard templates as a reference, you should
    provide matching macros and block names.

    For more information, see https://forge-allura.apache.org/p/allura/wiki/Themes%20in%20Allura/

    :var icons: a dictionary of sized icons for each tool
    '''

    master_template = 'allura:templates/jinja_master/master.html'
    jinja_macros = 'allura:templates/jinja_master/theme_macros.html'
    nav_menu = 'allura:templates/jinja_master/nav_menu.html'
    top_nav = 'allura:templates/jinja_master/top_nav.html'
    sidebar_menu = 'allura:templates/jinja_master/sidebar_menu.html'
    icons = {
        'subproject': {
            24: 'images/ext_24.png',
            32: 'images/ext_32.png',
            48: 'images/ext_48.png'
        }
    }

    def require(self):
        g.register_theme_css('css/site_style.css', compress=False)

    @classmethod
    def register_ew_resources(cls, manager, name):
        manager.register_directory(
            'theme/%s' % name,
            pkg_resources.resource_filename(
                'allura',
                os.path.join('nf', name)))

    def href(self, href, theme_name=None):
        '''
        Build a full URL for a given resource path
        :param href: a path like ``css/site_style.css``
        :param theme_name: defaults to current theme
        :return: a full URL
        '''
        if theme_name is None:
            theme_name = config.get('theme', 'allura')
        return g.resource_manager.absurl(f'theme/{theme_name}/{href}')

    @LazyProperty
    def personal_data_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
        '''
        from allura.lib.widgets.forms import PersonalDataForm
        return PersonalDataForm()

    @LazyProperty
    def add_telnumber_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page to
                 allow adding a telephone number.
        '''
        from allura.lib.widgets.forms import AddTelNumberForm
        return AddTelNumberForm()

    @LazyProperty
    def add_website_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page to
                 allow adding a personal website url.
        '''
        from allura.lib.widgets.forms import AddWebsiteForm
        return AddWebsiteForm()

    @LazyProperty
    def skype_account_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page to
                 allow setting the user's Skype account.
        '''
        from allura.lib.widgets.forms import SkypeAccountForm
        return SkypeAccountForm()

    @LazyProperty
    def remove_textvalue_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page to
                 allow removing a single text value from a list.
        '''
        from allura.lib.widgets.forms import RemoveTextValueForm
        return RemoveTextValueForm()

    @LazyProperty
    def add_socialnetwork_form(self):
        '''
        :return: None, or an easywidgets Form to render on  the user preferences page to
                 allow adding a social network account.
        '''
        from allura.lib.widgets.forms import AddSocialNetworkForm
        return AddSocialNetworkForm(action='/auth/preferences/add_social_network')

    @LazyProperty
    def remove_socialnetwork_form(self):
        '''
        :return: None, or an easywidgets Form to render on  the user preferences page to
                 allow removing a social network account.
        '''
        from allura.lib.widgets.forms import RemoveSocialNetworkForm
        return RemoveSocialNetworkForm(action='/auth/preferences/remove_social_network')

    @LazyProperty
    def add_timeslot_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
                 to allow creating a new availability timeslot
        '''
        from allura.lib.widgets.forms import AddTimeSlotForm
        return AddTimeSlotForm()

    @LazyProperty
    def remove_timeslot_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
                 to remove a timeslot
        '''
        from allura.lib.widgets.forms import RemoveTimeSlotForm
        return RemoveTimeSlotForm()

    @LazyProperty
    def add_inactive_period_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
                 to allow creating a new period of inactivity
        '''
        from allura.lib.widgets.forms import AddInactivePeriodForm
        return AddInactivePeriodForm()

    @LazyProperty
    def remove_inactive_period_form(self):
        '''
        :return: None, or an easywidgets Form to render on the user preferences page
                 to allow removing an existing period of inactivity
        '''
        from allura.lib.widgets.forms import RemoveInactivePeriodForm
        return RemoveInactivePeriodForm()

    @LazyProperty
    def add_trove_category(self):
        '''
        :return: None, or an easywidgets Form to render on the page to create a
                 new trove_category
        '''
        from allura.lib.widgets.forms import AddTroveCategoryForm
        return AddTroveCategoryForm(action='/categories/create')

    @LazyProperty
    def remove_trove_category(self):
        '''
        :return: None, or an easywidgets Form to render on the page to remove
                 an existing trove_category
        '''
        from allura.lib.widgets.forms import RemoveTroveCategoryForm
        return RemoveTroveCategoryForm(action='/categories/remove')

    @LazyProperty
    def add_user_skill(self):
        '''
        :return: None, or an easywidgets Form to render on the page to add a
                 new skill to a user profile
        '''
        from allura.lib.widgets.forms import AddUserSkillForm
        return AddUserSkillForm(action='/auth/user_info/skills/save_skill')

    @LazyProperty
    def select_subcategory_form(self):
        '''
        :return: None, or an easywidgets Form to render on the page to add a
                 new skill to a user profile, allowing to select a category in
                 order to see its sub-categories
        '''
        from allura.lib.widgets.forms import SelectSubCategoryForm
        return SelectSubCategoryForm(action='/auth/user_info/skills/')

    @LazyProperty
    def remove_user_skill(self):
        '''
        :return: None, or an easywidgets Form to render on the page to remove
                 an existing skill from a user profile
        '''
        from allura.lib.widgets.forms import RemoveSkillForm
        return RemoveSkillForm(action='/auth/user_info/skills/remove_skill')

    @property
    def master(self):
        return self.master_template

    @classmethod
    def get(cls):
        '''
        :rtype: ThemeProvider
        '''
        name = config.get('theme', 'allura')
        return g.entry_points['theme'][name]()

    def app_icon_url(self, app, size):
        """returns the default icon for the given app (or non-app thing like 'subproject').
            Takes an instance of class Application, or else a string.
            Expected to be overriden by derived Themes.
        """
        if isinstance(app, str):
            app = str(app)
        if isinstance(app, str):
            if app in self.icons and size in self.icons[app]:
                return g.theme_href(self.icons[app][size])
            elif app in g.entry_points['tool']:
                return g.entry_points['tool'][app].icon_url(size)
            else:
                return None
        else:
            return app.icon_url(size)

    def _get_site_notification(self, url='', user=None, tool_name='', site_notification_cookie_value=''):
        from allura.model.notification import SiteNotification
        cookie_info = {}
        try:
            for existing_cookie_chunk in site_notification_cookie_value.split('_'):
                note_id, views, closed = existing_cookie_chunk.split('-')
                views = asint(views)
                closed = asbool(closed)
                cookie_info[note_id] = (views, closed)
        except ValueError:
            # ignore any weird cookie data
            pass

        active_notes = SiteNotification.actives()
        note_to_show = None
        for note in active_notes:
            if note.user_role and (not user or user.is_anonymous()):
                continue
            if note.user_role:
                projects = user.my_projects_by_role_name(note.user_role)
                if len(projects) == 0 or len(projects) == 1 and projects[0].is_user_project:
                    continue

            if note.page_regex and re.search(note.page_regex, url) is None:
                continue
            if note.page_tool_type and tool_name.lower() != note.page_tool_type.lower():
                continue

            views_closed = cookie_info.get(str(note._id))
            if views_closed:
                views, closed = views_closed
            else:
                views = 0
                closed = False

            if closed or note.impressions > 0 and views > note.impressions:
                continue

            # this notification is ok to show, so this is the one.
            views += 1
            note_to_show = note
            cookie_info[str(note._id)] = (views, closed)
            break

        # remove any extraneous cookie chunks so it doesn't accumulate over time into a too-large cookie
        for note_id in list(cookie_info.keys()):
            if note_id not in [str(n._id) for n in active_notes]:
                del cookie_info[note_id]

        if note_to_show:
            cookie_chunks = []
            for note_id, views_closed in cookie_info.items():
                cookie_chunks.append(f'{note_id}-{views_closed[0]}-{views_closed[1]}')
            set_cookie_value = '_'.join(sorted(cookie_chunks))
            return note_to_show, set_cookie_value

    def get_site_notification(self):
        from tg import request, response
        tool_name = c.app.config.tool_name if c.app else ''
        r = self._get_site_notification(
            request.path_qs,
            c.user,
            tool_name,
            request.cookies.get('site-notification', '')
        )
        if not r:
            return None
        note, set_cookie = r

        response.set_cookie(
            'site-notification',
            set_cookie,
            secure=request.environ['beaker.session'].secure,
            max_age=timedelta(days=365))
        return note

    def use_input_placeholders(self):
        return False


class ResponsiveTheme(ThemeProvider):
    master_template = 'allura:templates_responsive/jinja_master/master.html'
    jinja_macros = 'allura:templates_responsive/jinja_master/theme_macros.html'
    nav_menu = 'allura:templates_responsive/jinja_master/nav_menu.html'
    top_nav = 'allura:templates_responsive/jinja_master/top_nav.html'
    sidebar_menu = 'allura:templates_responsive/jinja_master/sidebar_menu.html'

    def require(self):
        g.register_theme_css('css/styles.css', compress=False)


class LocalProjectRegistrationProvider(ProjectRegistrationProvider):
    pass


class UserPreferencesProvider:

    '''
    An interface for user preferences, like display_name and email_address

    To use a new provider, expose an entry point in setup.py::

        [allura.user_prefs]
        myprefs = foo.bar:MyUserPrefProvider

    Then in your .ini file, set user_prefs_storage.method=myprefs
    '''

    @classmethod
    def get(cls):
        '''
        :rtype: UserPreferencesProvider
        '''
        method = config.get('user_prefs_storage.method', 'local')
        return g.entry_points['user_prefs'][method]()

    def get_pref(self, user, pref_name):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :param str pref_name:
        :return: pref_value
        :raises: AttributeError if pref_name not found
        '''
        raise NotImplementedError('get_pref')

    def set_pref(self, user, pref_name, pref_value):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :param str pref_name:
        :param pref_value:
        '''
        raise NotImplementedError('set_pref')

    def additional_urls(self):
        '''
        Returns a mapping of additional routes for AuthProvider.

        By default, scans the provider for @expose()ed methods, which are
        added as pages with the same name as the method.  Note that if you
        want the new pages to show up in the menu on the various auth pages,
        you will also need to add it to the list returned by
        `AuthenticationProvider.account_navigation`.

        If you want to override this behavior, you can override this method
        and manually return a mapping of `{page_name: handler, ...}`.  Note,
        however, that this could break future subclasses of your providers'
        ability to extend the list.

        For example: `{'newroute', newroute_handler}` will add 'newroute'
        attribute to the auth controller, which will be set to `newroute_handler`.
        `newroute_handler` can either be an @expose()ed method, or a controller
        that can dispatch further sub-pages.

        `newroute_handler` must be decorated with @expose(), but does not have
        to live on the provider.
        '''
        urls = {}
        for attr_name in dir(self):
            attr_value = getattr(self, attr_name)
            decoration = getattr(attr_value, 'decoration', None)
            if getattr(decoration, 'exposed', False):
                urls[attr_name] = attr_value
        return urls

    def add_multivalue_pref(self, user, pref_name, entry):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :param str pref_name:
        :param entry: can be a simple value, or a dict structure
        :raises: AttributeError if pref_name not found
        '''
        self.get_pref(user, pref_name).append(entry)

    def remove_multivalue_pref(self, user, pref_name, entry):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :param str pref_name:
        :param entry: can be a simple value, or a dict structure
        :raises: AttributeError if pref_name not found
        :raises: ValueError if data not found
        '''
        self.get_pref(user, pref_name).remove(entry)


class LocalUserPreferencesProvider(UserPreferencesProvider):

    '''
    The default UserPreferencesProvider, storing preferences on the User object
    in mongo.
    '''

    def get_pref(self, user, pref_name):
        if pref_name in user.preferences:
            pref_value = user.preferences[pref_name]
        elif pref_name == 'display_name':
            # get the value directly from ming's internals, bypassing
            # FieldPropertyDisplayName which always calls back to this get_pref
            # method (infinite recursion)
            pref_value = user.__dict__['__ming__'].state.document.display_name
        else:
            pref_value = getattr(user, pref_name)

        if pref_name == 'email_format' and pref_value == 'html':
            # html-only is no longer supported
            pref_value = 'both'

        return pref_value

    def set_pref(self, user, pref_name, pref_value):
        if pref_name == 'display_name' and asbool(config.get('activitystream.recording.enabled', False)):
            activity_tasks.change_user_name.post(user._id, pref_value)

        if pref_name in user.preferences:
            user.preferences[pref_name] = pref_value
        else:
            setattr(user, pref_name, pref_value)


class LdapUserPreferencesProvider(UserPreferencesProvider):
    '''
    Store preferences in LDAP, falling back to LocalUserPreferencesProvider
    '''

    @LazyProperty
    def fields(self):
        return h.config_with_prefix(config, 'user_prefs_storage.ldap.fields.')

    def get_pref(self, user, pref_name, multi=False):
        from allura import model as M
        if pref_name in self.fields and user != M.User.anonymous():
            return self._get_pref(user.username, pref_name, multi=multi)
        else:
            return LocalUserPreferencesProvider().get_pref(user, pref_name)

    def _get_pref(self, username, pref_name, multi=False):
        con = ldap_conn()
        try:
            rs = con.search_s(ldap_user_dn(username), ldap.SCOPE_BASE)
        except ldap.NO_SUCH_OBJECT:
            rs = []
        else:
            con.unbind_s()
        if not rs:
            log.warning(f'LdapUserPref: No user record found for: {username}')
            return ''
        user_dn, user_attrs = rs[0]
        ldap_attr = self.fields[pref_name]
        attr_list = user_attrs.get(ldap_attr, [])
        if multi:
            return [attr.decode('utf-8', errors='replace') for attr in attr_list]
        elif attr_list:
            return attr_list[0].decode('utf-8', errors='replace')
        else:
            return ''

    def set_pref(self, user, pref_name, pref_value):
        if pref_name in self.fields:
            ldap_attr = self.fields[pref_name]
            if isinstance(pref_value, list):
                ldap_val = [v.encode('utf-8', errors='replace') for v in pref_value]
            else:
                ldap_val = pref_value.encode('utf-8', errors='replace')
            con = ldap_conn()
            con.modify_s(ldap_user_dn(user.username),
                         [(ldap.MOD_REPLACE, ldap_attr, ldap_val)])
            con.unbind_s()
        else:
            return LocalUserPreferencesProvider().set_pref(user, pref_name, pref_value)


class AdminExtension:

    """
    A base class for extending the admin areas in Allura.

    After extending this, expose the app by adding an entry point in your
    setup.py::

        [allura.admin]
        myadmin = foo.bar.baz:MyCustomAdmin

    :ivar dict project_admin_controllers: Mapping of str (url component) to
        Controllers.  Can be implemented as a ``@property`` function.  The str
        url components will be mounted at /p/someproject/admin/ext/STR/ and will
        invoke the Controller.
    """

    project_admin_controllers = {}

    def update_project_sidebar_menu(self, sidebar_links):
        """
        Implement this function to modify the project sidebar.
        Check `c.project` if you want to limit when this displays
        (e.g. nbhd project, subproject, etc)

        :param sidebar_links: project admin side bar links
        :type sidebar_links: list of :class:`allura.app.SitemapEntry`

        :rtype: ``None``
        """
        pass


class SiteAdminExtension:
    """
    A base class for extending the site admin area in Allura.

    After extending this, expose the extension by adding an entry point in your
    setup.py::

        [allura.site_admin]
        myext = foo.bar.baz:MySiteAdminExtension

    :ivar dict controllers: Mapping of str (url component) to
        Controllers.  Can be implemented as a ``@property`` function.  The str
        url components will be mounted at /nf/admin/STR/ and will
        invoke the Controller.
    """

    controllers = {}

    def update_sidebar_menu(self, sidebar_links):
        """
        Change the site admin sidebar by modifying ``sidebar_links``.

        :param sidebar_links: site admin side bar links
        :type sidebar_links: list of :class:`allura.app.SitemapEntry`

        :rtype: ``None``
        """
        pass


class ImportIdConverter:

    '''
    An interface to convert to and from import_id values for indexing,
    searching, or displaying.

    To provide a new converter, expose an entry point in setup.py:

        [allura.import_id_converter]
        mysource = foo.bar:SourceIdConverter

    Then in your .ini file, set import_id_converter=mysource
    '''

    @classmethod
    def get(cls):
        '''
        :rtype: ImportIdConverter
        '''
        converter = config.get('import_id_converter')
        if converter:
            return g.entry_points['allura.import_id_converter'][converter]()
        return cls()

    def simplify(self, import_id):
        if hasattr(import_id, 'get'):
            return import_id.get('source_id')
        return None

    def expand(self, source_id, app_instance):
        import_id = {
            'source_id': source_id,
        }
        import_id.update(app_instance.config.options.get('import_id', {}))
        return import_id
