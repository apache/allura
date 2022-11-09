# Licensed to the Apache Software Foundation (ASF) under one
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

import calendar
from base64 import b32encode
from datetime import datetime, time, timedelta
from time import time as time_time
import json

from six.moves.urllib.parse import urlparse, parse_qs
from six.moves.urllib.parse import urlencode

from bson import ObjectId
import re

from ming.orm.ormsession import ThreadLocalORMSession, session
from tg import config, expose
from mock import patch, Mock
import mock
import pytest
from tg import tmpl_context as c, app_globals as g

from allura.tests import TestController
from allura.tests import decorators as td
from allura.tests.decorators import audits, out_audits, assert_logmsg
from alluratest.controller import setup_trove_categories, TestRestApiBase, oauth1_webtest
from allura import model as M
from allura.model.oauth import dummy_oauths
from allura.lib import plugin
from allura.lib import helpers as h
from allura.lib.multifactor import TotpService, RecoveryCodeService


def unentity(s):
    return s.replace('&quot;', '"').replace('&#34;', '"')


class TestAuth(TestController):
    def test_login(self):
        self.app.get('/auth/')
        r = self.app.post('/auth/send_verification_link', params=dict(a='test@example.com',
                                                                      _session_id=self.app.cookies['_session_id']))
        email = M.User.query.get(username='test-admin').email_addresses[0]
        r = self.app.post('/auth/send_verification_link', params=dict(a=email,
                                                                      _session_id=self.app.cookies['_session_id']))
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/auth/verify_addr', params=dict(a='foo'))
        assert json.loads(self.webflash(r))['status'] == 'error', self.webflash(r)
        ea = M.EmailAddress.find({'email': email}).first()
        r = self.app.get('/auth/verify_addr', params=dict(a=ea.nonce))
        assert json.loads(self.webflash(r))['status'] == 'ok', self.webflash(r)
        r = self.app.get('/auth/logout')

        with audits('Successful login', user=True):
            r = self.app.post('/auth/do_login', params=dict(
                username='test-user', password='foo',
                _session_id=self.app.cookies['_session_id']),
                antispam=True).follow()
            assert r.headers['Location'] == 'http://localhost/dashboard'

        r = self.app.post('/auth/do_login', antispam=True, params=dict(
            username='test-user', password='foo', honey1='robot',  # bad honeypot value
            _session_id=self.app.cookies['_session_id']),
                          extra_environ={'regular_antispam_err_handling_even_when_tests': 'true'},
                          status=302)
        wf = json.loads(self.webflash(r))
        assert wf['status'] == 'error'
        assert wf['message'] == 'Spambot protection engaged'

        with audits('Failed login', user=True):
            r = self.app.post('/auth/do_login', antispam=True, params=dict(
                username='test-user', password='food',
                _session_id=self.app.cookies['_session_id']))
            assert 'Invalid login' in str(r), r.showbrowser()

        r = self.app.post('/auth/do_login', antispam=True, params=dict(
            username='test-usera', password='foo',
            _session_id=self.app.cookies['_session_id']))
        assert 'Invalid login' in str(r), r.showbrowser()

    def test_login_invalid_username(self):
        extra = {'username': '*anonymous'}
        r = self.app.get('/auth/', extra_environ=extra)
        f = r.forms[0]
        encoded = self.app.antispam_field_names(f)
        f[encoded['username']] = 'test@user.com'
        f[encoded['password']] = 'foo'
        r = f.submit(extra_environ={'username': '*anonymous'})
        r.mustcontain('Usernames only include small letters, ')

    def test_login_diff_ips_ok(self):
        # exercises AntiSpam.validate methods
        extra = {'username': '*anonymous', 'REMOTE_ADDR': '11.22.33.44'}
        r = self.app.get('/auth/', extra_environ=extra)

        f = r.forms[0]
        encoded = self.app.antispam_field_names(f)
        f[encoded['username']] = 'test-user'
        f[encoded['password']] = 'foo'
        with audits('Successful login', user=True):
            r = f.submit(extra_environ={'username': '*anonymous', 'REMOTE_ADDR': '11.22.33.99'})

    def test_login_diff_ips_bad(self):
        # exercises AntiSpam.validate methods
        extra = {'username': '*anonymous', 'REMOTE_ADDR': '24.52.32.123'}
        r = self.app.get('/auth/', extra_environ=extra)

        f = r.forms[0]
        encoded = self.app.antispam_field_names(f)
        f[encoded['username']] = 'test-user'
        f[encoded['password']] = 'foo'
        r = f.submit(extra_environ={'username': '*anonymous', 'REMOTE_ADDR': '11.22.33.99',
                                    'regular_antispam_err_handling_even_when_tests': 'true'},
                     status=302)
        wf = json.loads(self.webflash(r))
        assert wf['status'] == 'error'
        assert wf['message'] == 'Spambot protection engaged'

    @patch('allura.lib.plugin.AuthenticationProvider.hibp_password_check_enabled', Mock(return_value=True))
    @patch('allura.tasks.mail_tasks.sendsimplemail')
    def test_login_hibp_compromised_password_untrusted_client(self, sendsimplemail):
        # first & only login by this user, so won't have any trusted previous logins
        self.app.extra_environ = {'disable_auth_magic': 'True'}
        r = self.app.get('/auth/')
        f = r.forms[0]
        encoded = self.app.antispam_field_names(f)
        f[encoded['username']] = 'test-user'
        f[encoded['password']] = 'foo'

        with audits('Attempted login from untrusted location with password in HIBP breach database', user=True):
            r = f.submit(status=200)

        r.mustcontain('reset your password via email.')
        r.mustcontain('reset your password via email.<br>\nPlease check your email')

        args, kwargs = sendsimplemail.post.call_args
        assert sendsimplemail.post.call_count == 1
        assert kwargs['subject'] == 'Update your %s password' % config['site_name']
        assert '/auth/forgotten_password/' in kwargs['text']

        assert [] == M.UserLoginDetails.query.find().all()  # no records created

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    def test_login_hibp_compromised_password_trusted_client(self, sendsimplemail):
        self.app.extra_environ = {'disable_auth_magic': 'True'}

        # regular login first, so IP address will be recorded and then trusted
        r = self.app.get('/auth/')
        f = r.forms[0]
        encoded = self.app.antispam_field_names(f)
        f[encoded['username']] = 'test-user'
        f[encoded['password']] = 'foo'
        with audits('Successful login', user=True):
            f.submit(status=302)
        self.app.get('/auth/logout')

        # this login will get caught by HIBP check, but trusted due to IP address being same
        with patch('allura.lib.plugin.AuthenticationProvider.hibp_password_check_enabled', Mock(return_value=True)):
            r = self.app.get('/auth/')
            f = r.forms[0]
            encoded = self.app.antispam_field_names(f)
            f[encoded['username']] = 'test-user'
            f[encoded['password']] = 'foo'

            with audits(r'Successful login with password in HIBP breach database, from trusted source '
                        r'\(reason: exact ip\)', user=True):
                r = f.submit(status=302)

            assert r.session.get('pwd-expired')
            assert r.session.get('expired-reason') == 'hibp'
            assert r.location == 'http://localhost/auth/pwd_expired'

            r = r.follow()
            r.mustcontain('must be updated to be more secure')

            # changing password covered in TestPasswordExpire

    def test_login_disabled(self):
        u = M.User.query.get(username='test-user')
        u.disabled = True
        r = self.app.get('/auth/', extra_environ={'username': '*anonymous'})
        f = r.forms[0]
        encoded = self.app.antispam_field_names(f)
        f[encoded['username']] = 'test-user'
        f[encoded['password']] = 'foo'
        with audits('Failed login', user=True):
            r = f.submit(extra_environ={'username': '*anonymous'})

    def test_login_pending(self):
        u = M.User.query.get(username='test-user')
        u.pending = True
        r = self.app.get('/auth/', extra_environ={'username': '*anonymous'})
        f = r.forms[0]
        encoded = self.app.antispam_field_names(f)
        f[encoded['username']] = 'test-user'
        f[encoded['password']] = 'foo'
        with audits('Failed login', user=True):
            r = f.submit(extra_environ={'username': '*anonymous'})

    def test_login_overlay(self):
        r = self.app.get('/auth/login_fragment/', extra_environ={'username': '*anonymous'})
        f = r.forms[0]
        encoded = self.app.antispam_field_names(f)
        f[encoded['username']] = 'test-user'
        f[encoded['password']] = 'foo'
        with audits('Successful login', user=True):
            r = f.submit(extra_environ={'username': '*anonymous'})

    def test_logout(self):
        self.app.extra_environ = {'disable_auth_magic': 'True'}
        nav_pattern = ('nav', {'class': 'nav-main'})
        r = self.app.get('/auth/')

        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo',
            _session_id=self.app.cookies['_session_id']),
            extra_environ={'REMOTE_ADDR': '127.0.0.1'},
            antispam=True).follow().follow()

        logged_in_session = r.session['_id']
        links = r.html.find(*nav_pattern).findAll('a')
        assert links[-1].string == "Log Out"

        r = self.app.get('/auth/logout').follow().follow()
        logged_out_session = r.session['_id']
        assert logged_in_session is not logged_out_session
        links = r.html.find(*nav_pattern).findAll('a')
        assert links[-1].string == 'Log In'

    def test_track_login(self):
        user = M.User.by_username('test-user')
        assert user.last_access['login_date'] is None
        assert user.last_access['login_ip'] is None
        assert user.last_access['login_ua'] is None

        self.app.get('/').follow()  # establish session
        self.app.post('/auth/do_login',
                      headers={'User-Agent': 'browser'},
                      extra_environ={'REMOTE_ADDR': '127.0.0.1'},
                      params=dict(
                          username='test-user',
                          password='foo',
                          _session_id=self.app.cookies['_session_id'],
                      ),
                      antispam=True,
                      )
        user = M.User.by_username('test-user')
        assert user.last_access['login_date'] is not None
        assert user.last_access['login_ip'] == '127.0.0.1'
        assert user.last_access['login_ua'] == 'browser'

    def test_rememberme(self):
        username = M.User.query.get(username='test-user').username

        r = self.app.get('/').follow()  # establish session

        # Login as test-user with remember me checkbox off
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo',
            _session_id=self.app.cookies['_session_id'],
        ), antispam=True)
        assert r.session['username'] == username
        assert r.session['login_expires'] is True

        for header, contents in r.headerlist:
            if header == 'Set-cookie':
                assert 'expires' not in contents

        # Login as test-user with remember me checkbox on
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo', rememberme='on',
            _session_id=self.app.cookies['_session_id'],
        ), antispam=True)
        assert r.session['username'] == username
        assert r.session['login_expires'] is not True

        for header, contents in r.headerlist:
            if header == 'Set-cookie':
                assert 'expires' in contents

    @td.with_user_project('test-admin')
    def test_user_can_not_claim_duplicate_emails(self):
        email_address = 'test_abcd_123@domain.net'
        user = M.User.query.get(username='test-admin')
        addresses_number = len(user.email_addresses)
        self.app.get('/').follow()  # establish session
        self.app.post('/auth/preferences/update_emails',
                      params={
                          'new_addr.addr': email_address,
                          'new_addr.claim': 'Claim Address',
                          'primary_addr': 'test-admin@users.localhost',
                          'preferences.email_format': 'plain',
                          'password': 'foo',
                          '_session_id': self.app.cookies['_session_id'],
                      },
                      extra_environ=dict(username='test-admin'))

        assert M.EmailAddress.find(dict(email=email_address, claimed_by_user_id=user._id)).count() == 1
        r = self.app.post('/auth/preferences/update_emails',
                          params={
                              'new_addr.addr': email_address,
                              'new_addr.claim': 'Claim Address',
                              'primary_addr': 'test-admin@users.localhost',
                              'preferences.email_format': 'plain',
                              'password': 'foo',
                              '_session_id': self.app.cookies['_session_id'],
                          },
                          extra_environ=dict(username='test-admin'))

        assert json.loads(self.webflash(r))['status'] == 'error', self.webflash(r)
        assert M.EmailAddress.find(dict(email=email_address, claimed_by_user_id=user._id)).count() == 1
        assert len(M.User.query.get(username='test-admin').email_addresses) == addresses_number + 1

    @td.with_user_project('test-admin')
    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_user_added_claimed_address_by_other_user_confirmed(self, gen_message_id, sendsimplemail):
        self.app.get('/').follow()  # establish session
        email_address = 'test_abcd_123@domain.net'

        # test-user claimed & confirmed email address
        user = M.User.query.get(username='test-user')
        user.claim_address(email_address)
        email = M.EmailAddress.find(dict(email=email_address)).first()
        email.confirmed = True
        ThreadLocalORMSession.flush_all()

        # Claiming the same email address by test-admin
        # the email should be added to the email_addresses list but notifications should not be sent

        admin = M.User.query.get(username='test-admin')
        addresses_number = len(admin.email_addresses)
        r = self.app.post('/auth/preferences/update_emails',
                          params={
                              'new_addr.addr': email_address,
                              'new_addr.claim': 'Claim Address',
                              'primary_addr': 'test-admin@users.localhost',
                              'preferences.email_format': 'plain',
                              'password': 'foo',
                              '_session_id': self.app.cookies['_session_id'],
                          },
                          extra_environ=dict(username='test-admin'))

        assert json.loads(self.webflash(r))['status'] == 'ok'
        assert json.loads(self.webflash(r))['message'] == 'A verification email has been sent.  ' \
                                                          'Please check your email and click to confirm.'

        args, kwargs = sendsimplemail.post.call_args
        assert sendsimplemail.post.call_count == 1
        assert kwargs['toaddr'] == email_address
        assert kwargs['subject'] == '%s - Email address claim attempt' % config['site_name']
        assert "You tried to add %s to your Allura account, " \
               "but it is already claimed by your %s account." % (email_address, user.username) in kwargs['text']

        assert len(M.User.query.get(username='test-admin').email_addresses) == addresses_number + 1
        assert len(M.EmailAddress.find(dict(email=email_address)).all()) == 2

    @td.with_user_project('test-admin')
    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_user_added_claimed_address_by_other_user_not_confirmed(self, gen_message_id, sendsimplemail):
        email_address = 'test_abcd_1235@domain.net'

        # test-user claimed email address
        user = M.User.query.get(username='test-user')
        user.claim_address(email_address)
        email = M.EmailAddress.find(dict(email=email_address)).first()
        email.confirmed = False
        ThreadLocalORMSession.flush_all()
        # Claiming the same email address by test-admin
        # the email should be added to the email_addresses list but notifications should not be sent

        user1 = M.User.query.get(username='test-user-1')
        addresses_number = len(user1.email_addresses)
        self.app.get('/').follow()  # establish session
        r = self.app.post('/auth/preferences/update_emails',
                          params={
                              'new_addr.addr': email_address,
                              'new_addr.claim': 'Claim Address',
                              'primary_addr': 'test-user-1@users.localhost',
                              'preferences.email_format': 'plain',
                              'password': 'foo',
                              '_session_id': self.app.cookies['_session_id'],
                          },
                          extra_environ=dict(username='test-user-1'))

        assert json.loads(self.webflash(r))['status'] == 'ok'
        assert json.loads(self.webflash(r))['message'] == 'A verification email has been sent.  ' \
                                                          'Please check your email and click to confirm.'
        assert sendsimplemail.post.called
        assert len(M.User.query.get(username='test-user-1').email_addresses) == addresses_number + 1
        assert len(M.EmailAddress.find(dict(email=email_address)).all()) == 2

    @td.with_user_project('test-admin')
    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_user_cannot_claim_more_than_max_limit(self, gen_message_id, sendsimplemail):
        with h.push_config(config, **{'user_prefs.maximum_claimed_emails': '2'}):
            self.app.get('/').follow()  # establish session
            r = self.app.post('/auth/preferences/update_emails',
                              params={
                                  'new_addr.addr': 'test_abcd_1@domain.net',
                                  'new_addr.claim': 'Claim Address',
                                  'primary_addr': 'test-user-1@users.localhost',
                                  'preferences.email_format': 'plain',
                                  'password': 'foo',
                                  '_session_id': self.app.cookies['_session_id'],
                              },
                              extra_environ=dict(username='test-user-1'))
            assert json.loads(self.webflash(r))['status'] == 'ok'

            r = self.app.post('/auth/preferences/update_emails',
                              params={
                                  'new_addr.addr': 'test_abcd_2@domain.net',
                                  'new_addr.claim': 'Claim Address',
                                  'primary_addr': 'test-user-1@users.localhost',
                                  'preferences.email_format': 'plain',
                                  'password': 'foo',
                                  '_session_id': self.app.cookies['_session_id'],
                              },
                              extra_environ=dict(username='test-user-1'))

            assert json.loads(self.webflash(r))['status'] == 'error'
            assert json.loads(self.webflash(r))['message'] == 'You cannot claim more than 2 email addresses.'

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_verification_link_for_confirmed_email(self, gen_message_id, sendsimplemail):
        self.app.get('/').follow()  # establish session
        email_address = 'test_abcd@domain.net'

        # test-user claimed email address
        user = M.User.query.get(username='test-user')
        user.claim_address(email_address)
        email = M.EmailAddress.find(dict(email=email_address, claimed_by_user_id=user._id)).first()
        email.confirmed = True

        user1 = M.User.query.get(username='test-user-1')
        user1.claim_address(email_address)
        email = M.EmailAddress.find(dict(email=email_address, claimed_by_user_id=user1._id)).first()
        email.confirmed = False

        ThreadLocalORMSession.flush_all()

        r = self.app.post('/auth/send_verification_link',
                          params=dict(a=email_address, _session_id=self.app.cookies['_session_id']),
                          extra_environ=dict(username='test-user-1', _session_id=self.app.cookies['_session_id']))

        assert json.loads(self.webflash(r))['status'] == 'ok'
        assert json.loads(self.webflash(r))['message'] == 'Verification link sent'

        args, kwargs = sendsimplemail.post.call_args
        assert sendsimplemail.post.call_count == 1
        assert kwargs['toaddr'] == email_address
        assert kwargs['subject'] == '%s - Email address claim attempt' % config['site_name']
        assert "You tried to add %s to your Allura account, " \
               "but it is already claimed by your %s account." % (email_address, user.username) in kwargs['text']

    def test_invalidate_verification_link_if_email_was_confirmed(self):
        self.app.get('/').follow()  # establish session
        email_address = 'test_abcd@domain.net'

        # test-user claimed email address
        user = M.User.query.get(username='test-user')
        user.claim_address(email_address)
        email = M.EmailAddress.find(dict(email=email_address, claimed_by_user_id=user._id)).first()
        email.confirmed = False
        ThreadLocalORMSession.flush_all()

        self.app.post('/auth/send_verification_link',
                      params=dict(a=email_address,
                                  _session_id=self.app.cookies['_session_id']),
                      extra_environ=dict(username='test-user'))

        user1 = M.User.query.get(username='test-user-1')
        user1.claim_address(email_address)
        email1 = M.EmailAddress.find(dict(email=email_address, claimed_by_user_id=user1._id)).first()
        email1.confirmed = True
        ThreadLocalORMSession.flush_all()
        # Verify first email with the verification link
        r = self.app.get('/auth/verify_addr', params=dict(a=email.nonce),
                         extra_environ=dict(username='test-user'))

        assert json.loads(self.webflash(r))['status'] == 'error'
        email = M.EmailAddress.find(dict(email=email_address, claimed_by_user_id=user._id)).first()
        assert not email.confirmed

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_verify_addr_correct_session(self, gen_message_id, sendsimplemail):
        self.app.get('/').follow()  # establish session
        email_address = 'test_abcd@domain.net'

        # test-user claimed email address
        user = M.User.query.get(username='test-user')
        user.claim_address(email_address)
        email = M.EmailAddress.find(dict(email=email_address, claimed_by_user_id=user._id)).first()
        email.confirmed = False
        ThreadLocalORMSession.flush_all()

        self.app.post('/auth/send_verification_link',
                      params=dict(a=email_address,
                                  _session_id=self.app.cookies['_session_id']),
                      extra_environ=dict(username='test-user'))

        # logged out, gets redirected to login page
        r = self.app.get('/auth/verify_addr', params=dict(a=email.nonce),
                         extra_environ=dict(username='*anonymous'))
        assert '/auth/?return_to=%2Fauth%2Fverify_addr' in r.location

        # logged in as someone else
        r = self.app.get('/auth/verify_addr', params=dict(a=email.nonce),
                         extra_environ=dict(username='test-admin'))
        assert '/auth/?return_to=%2Fauth%2Fverify_addr' in r.location
        assert 'You must be logged in to the correct account' == json.loads(self.webflash(r))['message']
        assert 'warning' == json.loads(self.webflash(r))['status']

        # logged in as correct user
        r = self.app.get('/auth/verify_addr', params=dict(a=email.nonce),
                         extra_environ=dict(username='test-user'))
        assert 'confirmed' in json.loads(self.webflash(r))['message']
        assert 'ok' == json.loads(self.webflash(r))['status']

        # assert 'email added' notification email sent
        args, kwargs = sendsimplemail.post.call_args
        assert kwargs['toaddr'] == user._id
        assert kwargs['subject'] == 'New Email Address Added'

    @staticmethod
    def _create_password_reset_hash():
        """ Generates a password reset token for a given user.

        :return: User object
        :rtype: User
        """
        # test-user claimed email address
        user = M.User.by_username('test-admin')
        user.set_tool_data('AuthPasswordReset',
                           hash="generated_hash_value",
                           hash_expiry="04-08-2020")
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        session(user).flush(user)

        hash_expiry = user.get_tool_data('AuthPasswordReset', 'hash_expiry')
        assert hash == 'generated_hash_value'
        assert hash_expiry == '04-08-2020'
        return user

    @pytest.mark.parametrize(['change_params'], [
        pytest.param({'new_addr.addr': 'test_abcd@domain.net',  # Change primary address
                      'primary_addr': 'test@example.com'},
                     id='change_primary'),
        pytest.param({'new_addr.addr': 'test@example.com',  # Claim new address
                      'new_addr.claim': 'Claim Address',
                      'primary_addr': 'test-admin@users.localhost',
                      'password': 'foo',
                      'preferences.email_format': 'plain'},
                     id='claim_new'),
        pytest.param({'addr-1.ord': '1',  # remove test-admin@users.localhost
                      'addr-1.delete': 'on',
                      'addr-2.ord': '2',
                      'new_addr.addr': '',
                      'primary_addr': 'test-admin@users.localhost',
                      'password': 'foo',
                      'preferences.email_format': 'plain'},
                     id='remove_one'),
        pytest.param({'addr-1.ord': '1',  # Remove email
                      'addr-2.ord': '2',
                      'addr-2.delete': 'on',
                      'new_addr.addr': '',
                      'primary_addr': 'test-admin@users.localhost'},
                     id='remove_all'),
    ])
    def test_email_change_invalidates_token(self, change_params):
        """ Generates new token invalidation tests.

        The tests cover: changing, claiming, updating, removing email addresses.
        :returns: email_change_invalidates_token
        """
        user = self._create_password_reset_hash()
        session(user).flush(user)

        self.app.get('/').follow()  # establish session
        change_params['_session_id'] = self.app.cookies['_session_id']
        self.app.post('/auth/preferences/update_emails',
                      extra_environ=dict(username='test-admin'),
                      params=change_params)

        u = M.User.by_username('test-admin')
        print(u.get_tool_data('AuthPasswordReset', 'hash'))
        assert u.get_tool_data('AuthPasswordReset', 'hash') == ''
        assert u.get_tool_data('AuthPasswordReset', 'hash_expiry') == ''

    @td.with_user_project('test-admin')
    def test_change_password(self):
        self.app.get('/').follow()  # establish session
        # Get and assert user with password reset token.
        user = self._create_password_reset_hash()
        old_pass = user.get_pref('password')

        # Change password
        with audits('Password changed', user=True):
            self.app.post('/auth/preferences/change_password',
                          extra_environ=dict(username='test-admin'),
                          params={
                              'oldpw': 'foo',
                              'pw': 'asdfasdf',
                              'pw2': 'asdfasdf',
                              '_session_id': self.app.cookies['_session_id'],
                          })

        # Confirm password was changed.
        assert old_pass != user.get_pref('password')

        # Confirm any existing tokens were reset.
        assert user.get_tool_data('AuthPasswordReset', 'hash') == ''
        assert user.get_tool_data('AuthPasswordReset', 'hash_expiry') == ''

        # Confirm an email was sent
        tasks = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendsimplemail')).all()
        assert len(tasks) == 1
        assert tasks[0].kwargs['subject'] == 'Password Changed'
        assert 'The password for your' in tasks[0].kwargs['text']

    @patch('allura.lib.plugin.AuthenticationProvider.hibp_password_check_enabled', Mock(return_value=True))
    @td.with_user_project('test-admin')
    def test_change_password_hibp(self):
        self.app.get('/').follow()  # establish session
        # Get and assert user with password reset token.
        user = self._create_password_reset_hash()
        old_pass = user.get_pref('password')

        # Attempt change password with weak pwd
        r = self.app.post('/auth/preferences/change_password',
                          extra_environ=dict(username='test-admin'),
                          params={
                              'oldpw': 'foo',
                              'pw': 'password',
                              'pw2': 'password',
                              '_session_id': self.app.cookies['_session_id'],
                          })

        assert 'Unsafe' in str(r.headers)

        r = self.app.post('/auth/preferences/change_password',
                          extra_environ=dict(username='test-admin'),
                          params={
                              'oldpw': 'foo',
                              'pw': '3j84rhoirwnoiwrnoiw',
                              'pw2': '3j84rhoirwnoiwrnoiw',
                              '_session_id': self.app.cookies['_session_id'],
                          })
        assert 'Unsafe' not in str(r.headers)

        # Confirm password was changed.
        user = M.User.by_username('test-admin')
        assert old_pass != user.get_pref('password')

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    @td.with_user_project('test-admin')
    def test_prefs(self, gen_message_id, sendsimplemail):
        r = self.app.get('/auth/preferences/',
                         extra_environ=dict(username='test-admin'))
        # check preconditions of test data
        assert 'test@example.com' not in r
        assert 'test-admin@users.localhost' in r
        assert (M.User.query.get(username='test-admin').get_pref('email_address') ==
                     'test-admin@users.localhost')

        # add test@example
        with td.audits('New email address: test@example.com', user=True):
            r = self.app.post('/auth/preferences/update_emails',
                              extra_environ=dict(username='test-admin'),
                              params={
                                  'new_addr.addr': 'test@example.com',
                                  'new_addr.claim': 'Claim Address',
                                  'primary_addr': 'test-admin@users.localhost',
                                  'password': 'foo',
                                  'preferences.email_format': 'plain',
                                  '_session_id': self.app.cookies['_session_id'],
                              })
        r = self.app.get('/auth/preferences/')
        assert 'test@example.com' in r
        user = M.User.query.get(username='test-admin')
        assert user.get_pref('email_address') == 'test-admin@users.localhost'

        # remove test-admin@users.localhost
        with td.audits('Email address deleted: test-admin@users.localhost', user=True):
            r = self.app.post('/auth/preferences/update_emails',
                              extra_environ=dict(username='test-admin'),
                              params={
                                  'addr-1.ord': '1',
                                  'addr-1.delete': 'on',
                                  'addr-2.ord': '2',
                                  'new_addr.addr': '',
                                  'primary_addr': 'test-admin@users.localhost',
                                  'password': 'foo',
                                  'preferences.email_format': 'plain',
                                  '_session_id': self.app.cookies['_session_id'],
                              })

        # assert 'email_removed' notification email sent
        args, kwargs = sendsimplemail.post.call_args
        assert kwargs['toaddr'] == user._id
        assert kwargs['subject'] == 'Email Address Removed'

        r = self.app.get('/auth/preferences/')
        assert 'test-admin@users.localhost' not in r
        # preferred address has not changed if email is not verified
        user = M.User.query.get(username='test-admin')
        assert user.get_pref('email_address') is None

        with td.audits('Display Name changed Test Admin => Admin', user=True):
            r = self.app.post('/auth/preferences/update',
                              params={'preferences.display_name': 'Admin',
                                      '_session_id': self.app.cookies['_session_id'],
                                      },
                              extra_environ=dict(username='test-admin'))

    @td.with_user_project('test-admin')
    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_email_prefs_change_requires_password(self, gen_message_id, sendsimplemail):
        self.app.get('/').follow()  # establish session
        # Claim new email
        new_email_params = {
            'new_addr.addr': 'test@example.com',
            'new_addr.claim': 'Claim Address',
            'primary_addr': 'test-admin@users.localhost',
            '_session_id': self.app.cookies['_session_id'],
        }
        r = self.app.post('/auth/preferences/update_emails',
                          params=new_email_params,
                          extra_environ=dict(username='test-admin'))
        assert 'You must provide your current password to claim new email' in self.webflash(r)
        assert 'test@example.com' not in r.follow()
        new_email_params['password'] = 'bad pass'

        r = self.app.post('/auth/preferences/update_emails',
                          params=new_email_params,
                          extra_environ=dict(username='test-admin'))
        assert 'You must provide your current password to claim new email' in self.webflash(r)
        assert 'test@example.com' not in r.follow()
        new_email_params['password'] = 'foo'  # valid password

        r = self.app.post('/auth/preferences/update_emails',
                          params=new_email_params,
                          extra_environ=dict(username='test-admin'))
        assert 'You must provide your current password to claim new email' not in self.webflash(r)
        assert 'test@example.com' in r.follow()

        # Change primary address
        change_primary_params = {
            'new_addr.addr': '',
            'primary_addr': 'test@example.com',
            '_session_id': self.app.cookies['_session_id'],
        }
        r = self.app.post('/auth/preferences/update_emails',
                          params=change_primary_params,
                          extra_environ=dict(username='test-admin'))
        assert 'You must provide your current password to change primary address' in self.webflash(r)
        assert M.User.by_username('test-admin').get_pref('email_address') == 'test-admin@users.localhost'
        change_primary_params['password'] = 'bad pass'

        r = self.app.post('/auth/preferences/update_emails',
                          params=change_primary_params,
                          extra_environ=dict(username='test-admin'))
        assert 'You must provide your current password to change primary address' in self.webflash(r)
        assert M.User.by_username('test-admin').get_pref('email_address') == 'test-admin@users.localhost'
        change_primary_params['password'] = 'foo'  # valid password

        self.app.get('/auth/preferences/')  # let previous 'flash' message cookie get used up
        r = self.app.post('/auth/preferences/update_emails',
                          params=change_primary_params,
                          extra_environ=dict(username='test-admin'))
        assert 'You must provide your current password to change primary address' not in self.webflash(r)
        assert M.User.by_username('test-admin').get_pref('email_address') == 'test@example.com'

        # assert 'email added' notification email sent using original primary addr
        args, kwargs = sendsimplemail.post.call_args
        assert kwargs['toaddr'] == 'test-admin@users.localhost'
        assert kwargs['subject'] == 'Primary Email Address Changed'

        # Remove email
        remove_email_params = {
            'addr-1.ord': '1',
            'addr-2.ord': '2',
            'addr-2.delete': 'on',
            'new_addr.addr': '',
            'primary_addr': 'test-admin@users.localhost',
            '_session_id': self.app.cookies['_session_id'],
        }
        r = self.app.post('/auth/preferences/update_emails',
                          params=remove_email_params,
                          extra_environ=dict(username='test-admin'))
        assert 'You must provide your current password to delete an email' in self.webflash(r)
        assert 'test@example.com' in r.follow()
        remove_email_params['password'] = 'bad pass'
        r = self.app.post('/auth/preferences/update_emails',
                          params=remove_email_params,
                          extra_environ=dict(username='test-admin'))
        assert 'You must provide your current password to delete an email' in self.webflash(r)
        assert 'test@example.com' in r.follow()
        remove_email_params['password'] = 'foo'  # vallid password
        r = self.app.post('/auth/preferences/update_emails',
                          params=remove_email_params,
                          extra_environ=dict(username='test-admin'))
        assert 'You must provide your current password to delete an email' not in self.webflash(r)
        assert 'test@example.com' not in r.follow()

    @td.with_user_project('test-admin')
    def test_prefs_subscriptions(self):
        r = self.app.get('/auth/subscriptions/',
                         extra_environ=dict(username='test-admin'))
        subscriptions = M.Mailbox.query.find(dict(
            user_id=c.user._id, is_flash=False)).all()
        # make sure page actually lists all the user's subscriptions
        assert len(subscriptions) > 0, 'Test user has no subscriptions, cannot verify that they are shown'
        for m in subscriptions:
            assert str(m._id) in r, "Page doesn't list subscription for Mailbox._id = %s" % m._id

        # make sure page lists all tools which user can subscribe
        user = M.User.query.get(username='test-admin')
        for p in user.my_projects():
            for ac in p.app_configs:
                if not M.Mailbox.subscribed(project_id=p._id, app_config_id=ac._id):
                    if ac.tool_name in ('activity', 'admin', 'search', 'userstats', 'profile'):
                        # these have has_notifications=False
                        assert str(ac._id) not in r, "Page lists tool %s but it should not" % ac.tool_name
                    else:
                        assert str(ac._id) in r, "Page doesn't list tool %s" % ac.tool_name

    @td.with_user_project('test-admin')
    def test_update_user_notifications(self):
        self.app.get('/').follow()  # establish session
        assert not M.User.query.get(username='test-admin').get_pref('mention_notifications')
        self.app.post('/auth/subscriptions/update_user_notifications',
                      params={'_session_id': self.app.cookies['_session_id'],
                              })
        assert not M.User.query.get(username='test-admin').get_pref('mention_notifications')
        self.app.post('/auth/subscriptions/update_user_notifications',
                      params={'allow_umnotif': 'on',
                              '_session_id': self.app.cookies['_session_id'],
                              })
        assert M.User.query.get(username='test-admin').get_pref('mention_notifications')

    def _find_subscriptions_form(self, r):
        form = None
        for f in r.forms.values():
            if f.action == 'update_subscriptions':
                form = f
                break
        assert form is not None, "Can't find subscriptions form"
        return form

    def _find_subscriptions_field(self, form, subscribed=False):
        field_name = None
        for k, v in form.fields.items():
            if subscribed:
                check = v and v[0].value == 'on'
            else:
                check = v and v[0].value != 'on'
            if k and k.endswith('.subscribed') and check:
                field_name = k.replace('.subscribed', '')
        assert field_name, "Can't find unsubscribed tool for user"
        return field_name

    @td.with_user_project('test-admin')
    def test_prefs_subscriptions_subscribe(self):
        resp = self.app.get('/auth/subscriptions/',
                            extra_environ=dict(username='test-admin'))
        form = self._find_subscriptions_form(resp)
        # find not subscribed tool, subscribe and verify
        field_name = self._find_subscriptions_field(form, subscribed=False)
        t_id = ObjectId(form.fields[field_name + '.tool_id'][0].value)
        p_id = ObjectId(form.fields[field_name + '.project_id'][0].value)
        subscribed = M.Mailbox.subscribed(project_id=p_id, app_config_id=t_id)
        assert not subscribed, "User already subscribed for tool %s" % t_id
        form.fields[field_name + '.subscribed'][0].value = 'on'
        form.submit()
        subscribed = M.Mailbox.subscribed(project_id=p_id, app_config_id=t_id)
        assert subscribed, "User is not subscribed for tool %s" % t_id

    @td.with_user_project('test-admin')
    def test_prefs_subscriptions_unsubscribe(self):
        resp = self.app.get('/auth/subscriptions/',
                            extra_environ=dict(username='test-admin'))
        form = self._find_subscriptions_form(resp)
        field_name = self._find_subscriptions_field(form, subscribed=True)
        s_id = ObjectId(form.fields[field_name + '.subscription_id'][0].value)
        s = M.Mailbox.query.get(_id=s_id)
        assert s, "User has not subscription with Mailbox._id = %s" % s_id
        form.fields[field_name + '.subscribed'][0].value = None
        form.submit()
        s = M.Mailbox.query.get(_id=s_id)
        assert not s, "User still has subscription with Mailbox._id %s" % s_id

    def test_format_email(self):
        self.app.get('/').follow()  # establish session
        self.app.post('/auth/subscriptions/update_subscriptions',
                      params={'email_format': 'plain', 'subscriptions': '',
                              '_session_id': self.app.cookies['_session_id']})
        r = self.app.get('/auth/subscriptions/')
        assert '<option selected value="plain">Plain Text</option>' in r
        self.app.post('/auth/subscriptions/update_subscriptions',
                      params={'email_format': 'both', 'subscriptions': '',
                              '_session_id': self.app.cookies['_session_id']})
        r = self.app.get('/auth/subscriptions/')
        assert '<option selected value="both">HTML</option>' in r

    def test_create_account(self):
        r = self.app.get('/auth/create_account')
        assert 'Create an Account' in r
        r = self.app.post('/auth/save_new',
                          params=dict(username='AAA', pw='123',
                                      _session_id=self.app.cookies['_session_id']))
        assert 'Enter a value 6 characters long or more' in r
        assert ('Usernames must include only small letters, numbers, '
                  'and dashes. They must also start with a letter and be '
                  'at least 3 characters long.' in r)
        r = self.app.post(
            '/auth/save_new',
            params=dict(
                username='aaa',
                pw='12345678',
                pw2='12345678',
                display_name='Test Me',
                _session_id=self.app.cookies['_session_id'],
            ))
        r = r.follow().follow()
        assert 'User "aaa" registered' in unentity(r.text)
        r = self.app.post(
            '/auth/save_new',
            params=dict(
                username='aaa',
                pw='12345678',
                pw2='12345678',
                display_name='Test Me',
                _session_id=self.app.cookies['_session_id'],
            ))
        assert 'That username is already taken. Please choose another.' in r
        r = self.app.get('/auth/logout')
        r = self.app.post(
            '/auth/do_login',
            params=dict(username='aaa', password='12345678',
                        _session_id=self.app.cookies['_session_id']), antispam=True,
            status=302)

    def test_create_account_require_email(self):
        self.app.get('/').follow()  # establish session
        with h.push_config(config, **{'auth.require_email_addr': 'false'}):
            self.app.post(
                '/auth/save_new',
                params=dict(
                    username='aaa',
                    pw='12345678',
                    pw2='12345678',
                    display_name='Test Me',
                    email='test@example.com',
                    _session_id=self.app.cookies['_session_id'],
                ))
            user = M.User.query.get(username='aaa')
            assert not user.pending
            assert M.Project.query.find({'name': 'u/aaa'}).count() == 1
        with h.push_config(config, **{'auth.require_email_addr': 'true'}):
            self.app.post(
                '/auth/save_new',
                params=dict(
                    username='bbb',
                    pw='12345678',
                    pw2='12345678',
                    display_name='Test Me',
                    email='test@example.com',
                    _session_id=self.app.cookies['_session_id']
                ))
            user = M.User.query.get(username='bbb')
            assert user.pending
            assert M.Project.query.find({'name': 'u/bbb'}).count() == 0

    def test_verify_email(self):
        with h.push_config(config, **{'auth.require_email_addr': 'true'}):
            self.app.get('/').follow()  # establish session
            r = self.app.post(
                '/auth/save_new',
                params=dict(
                    username='aaa',
                    pw='12345678',
                    pw2='12345678',
                    display_name='Test Me',
                    email='test@example.com',
                    _session_id=self.app.cookies['_session_id']
                ))
            r = r.follow()
            user = M.User.query.get(username='aaa')
            em = M.EmailAddress.get(email='test@example.com')
            assert user._id == em.claimed_by_user_id
            r = self.app.get('/auth/verify_addr', params=dict(a=em.nonce))
            user = M.User.query.get(username='aaa')
            em = M.EmailAddress.get(email='test@example.com')
            assert not user.pending
            assert em.confirmed
            assert user.get_pref('email_address')
            assert M.Project.query.find({'name': 'u/aaa'}).count() == 1

    def test_create_account_disabled_header_link(self):
        with h.push_config(config, **{'auth.allow_user_registration': 'false'}):
            r = self.app.get('/')
            assert 'Register' not in r

    def test_create_account_disabled_form_gone(self):
        with h.push_config(config, **{'auth.allow_user_registration': 'false'}):
            r = self.app.get('/auth/create_account', status=404)
            assert 'Create an Account' not in r

    def test_create_account_disabled_submit_fails(self):
        with h.push_config(config, **{'auth.allow_user_registration': 'false'}):
            self.app.get('/').follow()  # establish session
            self.app.post('/auth/save_new',
                          params=dict(
                              username='aaa',
                              pw='12345678',
                              pw2='12345678',
                              display_name='Test Me',
                              _session_id=self.app.cookies['_session_id']
                          ),
                          status=404)

    def test_one_project_role(self):
        """Make sure when a user goes to a new project only one project role is created.
           There was an issue with extra project roles getting created if a user went directly to
           an admin page."""
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        self.app.get('/').follow()  # establish session
        self.app.post('/auth/save_new', params=dict(
            username='aaa',
            pw='12345678',
            pw2='12345678',
            display_name='Test Me',
            email='test@example.com',
            _session_id=self.app.cookies['_session_id'],
        )).follow()
        user = M.User.query.get(username='aaa')
        user.pending = False
        session(user).flush(user)
        assert M.ProjectRole.query.find(
            dict(user_id=user._id, project_id=p._id)).count() == 0

        self.app.get('/p/test/admin/permissions',
                     extra_environ=dict(username='aaa'), status=403)
        assert M.ProjectRole.query.find(
            dict(user_id=user._id, project_id=p._id)).count() <= 1

    def test_default_lookup(self):
        # Make sure that default _lookup() throws 404
        self.app.get('/auth/foobar', status=404)

    def test_disabled_user(self):
        user = M.User.query.get(username='test-admin')
        sess = session(user)
        assert not user.disabled
        r = self.app.get('/p/test/admin/',
                         extra_environ={'username': 'test-admin'})
        assert r.status_int == 200, 'Redirect to %s' % r.location
        user.disabled = True
        sess.save(user)
        sess.flush()
        user = M.User.query.get(username='test-admin')
        assert user.disabled
        r = self.app.get('/p/test/admin/',
                         extra_environ={'username': 'test-admin'})
        assert r.status_int == 302
        assert r.location == 'http://localhost/auth/?return_to=%2Fp%2Ftest%2Fadmin%2F'

    def test_no_open_return_to(self):
        r = self.app.get('/auth/logout').follow().follow()
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo',
            return_to='/foo',
            _session_id=self.app.cookies['_session_id']),
            antispam=True
        )
        assert r.location == 'http://localhost/foo'

        r = self.app.get('/auth/logout')
        r = self.app.post('/auth/do_login', antispam=True, params=dict(
            username='test-user', password='foo',
            return_to='http://localhost/foo',
            _session_id=self.app.cookies['_session_id']))
        assert r.location == 'http://localhost/foo'

        r = self.app.get('/auth/logout')
        r = self.app.post('/auth/do_login', antispam=True, params=dict(
            username='test-user', password='foo',
            return_to='http://example.com/foo',
            _session_id=self.app.cookies['_session_id'])).follow()
        assert r.location == 'http://localhost/dashboard'

        r = self.app.get('/auth/logout')
        r = self.app.post('/auth/do_login', antispam=True, params=dict(
            username='test-user', password='foo',
            return_to='//example.com/foo',
            _session_id=self.app.cookies['_session_id'])).follow()
        assert r.location == 'http://localhost/dashboard'

    def test_no_injected_headers_in_return_to(self):
        r = self.app.get('/auth/logout').follow().follow()
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo',
            return_to='/foo\nContent-Length: 777',
            # WebTest actually will raise an error if there's an invalid header (webob itself does not)
            _session_id=self.app.cookies['_session_id']),
            antispam=True
        )
        assert r.location == 'http://localhost/'
        assert r.content_length != 777


class TestAuthRest(TestRestApiBase):

    def test_tools_list_anon(self):
        resp = self.api_get('/rest/auth/tools/wiki', user='*anonymous')
        assert resp.json == {
            'tools': []
        }

    def test_tools_list_invalid_tool(self):
        resp = self.api_get('/rest/auth/tools/af732q9547235')
        assert resp.json == {
            'tools': []
        }

    @td.with_tool('test', 'Wiki', mount_point='docs', mount_label='Documentation')
    def test_tools_list_wiki(self):
        resp = self.api_get('/rest/auth/tools/wiki')
        assert resp.json == {
            'tools': [
                {
                    'mount_label': 'Wiki',
                    'mount_point': 'wiki',
                    'name': 'wiki',
                    'project_name': 'Home Project for Adobe',
                    'url': 'http://localhost/adobe/wiki/',
                    'api_url': 'http://localhost/rest/adobe/wiki/',
                },
                {
                    'mount_label': 'Documentation',
                    'mount_point': 'docs',
                    'name': 'wiki',
                    'project_name': 'Test Project',
                    'url': 'http://localhost/p/test/docs/',
                    'api_url': 'http://localhost/rest/p/test/docs/',
                },
            ]
        }


class TestPreferences(TestController):
    @td.with_user_project('test-admin')
    def test_personal_data(self):
        from pytz import country_names

        setsex, setbirthdate, setcountry, setcity, settimezone = \
            ('Male', '19/08/1988', 'IT', 'Milan', 'Europe/Rome')
        self.app.get('/auth/user_info/')

        # Check if personal data is properly set
        r = self.app.post('/auth/user_info/change_personal_data',
                          params=dict(
                              sex=setsex,
                              birthdate=setbirthdate,
                              country=setcountry,
                              city=setcity,
                              timezone=settimezone,
                              _session_id=self.app.cookies['_session_id'],
                          ))
        user = M.User.query.get(username='test-admin')
        sex = user.sex
        assert sex == setsex
        birthdate = user.birthdate.strftime('%d/%m/%Y')
        assert birthdate == setbirthdate
        country = user.localization.country
        assert country_names.get(setcountry) == country
        city = user.localization.city
        assert city == setcity
        timezone = user.timezone
        assert timezone == settimezone

        # Check if setting a wrong date everything works correctly
        r = self.app.post('/auth/user_info/change_personal_data',
                          params=dict(birthdate='30/02/1998', _session_id=self.app.cookies['_session_id']))
        assert 'Please enter a valid date' in r.text
        user = M.User.query.get(username='test-admin')
        sex = user.sex
        assert sex == setsex
        birthdate = user.birthdate.strftime('%d/%m/%Y')
        assert birthdate == setbirthdate
        country = user.localization.country
        assert country_names.get(setcountry) == country
        city = user.localization.city
        assert city == setcity
        timezone = user.timezone
        assert timezone == settimezone

        # Check deleting birthdate
        r = self.app.post('/auth/user_info/change_personal_data',
                          params=dict(
                              sex=setsex,
                              birthdate='',
                              country=setcountry,
                              city=setcity,
                              timezone=settimezone,
                              _session_id=self.app.cookies['_session_id'],
                          ))
        user = M.User.query.get(username='test-admin')
        assert user.birthdate is None

    @td.with_user_project('test-admin')
    def test_contacts(self):
        # Add skype account
        testvalue = 'testaccount'
        self.app.get('/auth/user_info/contacts/')
        self.app.post('/auth/user_info/contacts/skype_account',
                      params=dict(skypeaccount=testvalue, _session_id=self.app.cookies['_session_id']))
        user = M.User.query.get(username='test-admin')
        assert user.skypeaccount == testvalue

        # Add social network account
        socialnetwork = 'Facebook'
        accounturl = 'http://www.facebook.com/test'
        self.app.post('/auth/user_info/contacts/add_social_network',
                      params=dict(socialnetwork=socialnetwork,
                                  accounturl=accounturl,
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 1
        assert user.socialnetworks[0].socialnetwork == socialnetwork
        assert user.socialnetworks[0].accounturl == accounturl

        # Add second social network account
        socialnetwork2 = 'Twitter'
        accounturl2 = 'http://twitter.com/test'
        self.app.post('/auth/user_info/contacts/add_social_network',
                      params=dict(socialnetwork=socialnetwork2,
                                  accounturl='@test',
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 2
        assert {'socialnetwork': socialnetwork, 'accounturl': accounturl} in user.socialnetworks
        assert {'socialnetwork': socialnetwork2, 'accounturl': accounturl2} in user.socialnetworks

        # Remove first social network account
        self.app.post('/auth/user_info/contacts/remove_social_network',
                      params=dict(socialnetwork=socialnetwork,
                                  account=accounturl,
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 1
        assert {'socialnetwork': socialnetwork2, 'accounturl': accounturl2} in user.socialnetworks

        # Add empty social network account
        self.app.post('/auth/user_info/contacts/add_social_network',
                      params=dict(accounturl=accounturl, socialnetwork='',
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 1
        assert {'socialnetwork': socialnetwork2, 'accounturl': accounturl2} in user.socialnetworks

        # Add invalid social network account
        self.app.post('/auth/user_info/contacts/add_social_network',
                      params=dict(accounturl=accounturl, socialnetwork='invalid',
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 1
        assert {'socialnetwork': socialnetwork2, 'accounturl': accounturl2} in user.socialnetworks

        # Add telephone number
        telnumber = '+3902123456'
        self.app.post('/auth/user_info/contacts/add_telnumber',
                      params=dict(newnumber=telnumber,
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert (len(user.telnumbers) == 1 and (user.telnumbers[0] == telnumber))

        # Add second telephone number
        telnumber2 = '+3902654321'
        self.app.post('/auth/user_info/contacts/add_telnumber',
                      params=dict(newnumber=telnumber2,
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert (len(user.telnumbers) == 2 and telnumber in user.telnumbers and telnumber2 in user.telnumbers)

        # Remove first telephone number
        self.app.post('/auth/user_info/contacts/remove_telnumber',
                      params=dict(oldvalue=telnumber,
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert (len(user.telnumbers) == 1 and telnumber2 in user.telnumbers)

        # Add website
        website = 'http://www.testurl.com'
        self.app.post('/auth/user_info/contacts/add_webpage',
                      params=dict(newwebsite=website,
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert (len(user.webpages) == 1 and (website in user.webpages))

        # Add second website
        website2 = 'http://www.testurl2.com'
        self.app.post('/auth/user_info/contacts/add_webpage',
                      params=dict(newwebsite=website2,
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert (len(user.webpages) == 2 and website in user.webpages and website2 in user.webpages)

        # Remove first website
        self.app.post('/auth/user_info/contacts/remove_webpage',
                      params=dict(oldvalue=website,
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert (len(user.webpages) == 1 and website2 in user.webpages)

    @td.with_user_project('test-admin')
    def test_availability(self):
        # Add availability timeslot
        weekday = 'Monday'
        starttime = time(9, 0, 0)
        endtime = time(12, 0, 0)

        self.app.get('/auth/user_info/availability/')
        r = self.app.post('/auth/user_info/availability/add_timeslot',
                          params=dict(
                              weekday=weekday,
                              starttime=starttime.strftime('%H:%M'),
                              endtime=endtime.strftime('%H:%M'),
                              _session_id=self.app.cookies['_session_id'],
                          ))
        user = M.User.query.get(username='test-admin')
        timeslot1dict = dict(week_day=weekday, start_time=starttime, end_time=endtime)
        assert len(user.availability) == 1 and timeslot1dict in user.get_availability_timeslots()

        weekday2 = 'Tuesday'
        starttime2 = time(14, 0, 0)
        endtime2 = time(16, 0, 0)

        # Add second availability timeslot
        r = self.app.post('/auth/user_info/availability/add_timeslot',
                          params=dict(
                              weekday=weekday2,
                              starttime=starttime2.strftime('%H:%M'),
                              endtime=endtime2.strftime('%H:%M'),
                              _session_id=self.app.cookies['_session_id'],
                          ))
        user = M.User.query.get(username='test-admin')
        timeslot2dict = dict(week_day=weekday2, start_time=starttime2, end_time=endtime2)
        assert len(user.availability) == 2
        assert timeslot1dict in user.get_availability_timeslots()
        assert timeslot2dict in user.get_availability_timeslots()

        # Remove availability timeslot
        r = self.app.post('/auth/user_info/availability/remove_timeslot',
                          params=dict(
                              weekday=weekday,
                              starttime=starttime.strftime('%H:%M'),
                              endtime=endtime.strftime('%H:%M'),
                              _session_id=self.app.cookies['_session_id'],
                          ))
        user = M.User.query.get(username='test-admin')
        assert len(user.availability) == 1 and timeslot2dict in user.get_availability_timeslots()

        # Add invalid availability timeslot
        r = self.app.post('/auth/user_info/availability/add_timeslot',
                          params=dict(
                              weekday=weekday2,
                              starttime=endtime2.strftime('%H:%M'),
                              endtime=starttime2.strftime('%H:%M'),
                              _session_id=self.app.cookies['_session_id'],
                          ))
        assert 'Invalid period:' in str(r)
        user = M.User.query.get(username='test-admin')
        timeslot2dict = dict(week_day=weekday2, start_time=starttime2, end_time=endtime2)
        assert len(user.availability) == 1 and timeslot2dict in user.get_availability_timeslots()

    @td.with_user_project('test-admin')
    def test_inactivity(self):
        # Add inactivity period
        now = datetime.utcnow().date()
        now = datetime(now.year, now.month, now.day)
        startdate = now + timedelta(days=1)
        enddate = now + timedelta(days=7)
        self.app.get('/auth/user_info/availability/')
        r = self.app.post('/auth/user_info/availability/add_inactive_period',
                          params=dict(
                              startdate=startdate.strftime('%d/%m/%Y'),
                              enddate=enddate.strftime('%d/%m/%Y'),
                              _session_id=self.app.cookies['_session_id'],
                          ))
        user = M.User.query.get(username='test-admin')
        period1dict = dict(start_date=startdate, end_date=enddate)
        assert len(user.inactiveperiod) == 1 and period1dict in user.get_inactive_periods()

        # Add second inactivity period
        startdate2 = now + timedelta(days=24)
        enddate2 = now + timedelta(days=28)
        r = self.app.post('/auth/user_info/availability/add_inactive_period',
                          params=dict(
                              startdate=startdate2.strftime('%d/%m/%Y'),
                              enddate=enddate2.strftime('%d/%m/%Y'),
                              _session_id=self.app.cookies['_session_id'],
                          ))
        user = M.User.query.get(username='test-admin')
        period2dict = dict(start_date=startdate2, end_date=enddate2)
        assert len(user.inactiveperiod) == 2
        assert period1dict in user.get_inactive_periods()
        assert period2dict in user.get_inactive_periods()

        # Remove first inactivity period
        r = self.app.post(
            '/auth/user_info/availability/remove_inactive_period',
            params=dict(
                startdate=startdate.strftime('%d/%m/%Y'),
                enddate=enddate.strftime('%d/%m/%Y'),
                _session_id=self.app.cookies['_session_id'],
            ))
        user = M.User.query.get(username='test-admin')
        assert len(user.inactiveperiod) == 1 and period2dict in user.get_inactive_periods()

        # Add invalid inactivity period
        r = self.app.post('/auth/user_info/availability/add_inactive_period',
                          params=dict(
                              startdate='NOT/A/DATE',
                              enddate=enddate2.strftime('%d/%m/%Y'),
                              _session_id=self.app.cookies['_session_id'],
                          ))
        user = M.User.query.get(username='test-admin')
        assert 'Please enter a valid date' in str(r)
        assert len(user.inactiveperiod) == 1 and period2dict in user.get_inactive_periods()

    @td.with_user_project('test-admin')
    def test_skills(self):
        setup_trove_categories()
        # Add a skill
        skill_cat = M.TroveCategory.query.get(show_as_skill=True)
        level = 'low'
        comment = 'test comment'
        self.app.get('/auth/user_info/skills/')
        self.app.post('/auth/user_info/skills/save_skill',
                      params=dict(
                          level=level,
                          comment=comment,
                          selected_skill=str(skill_cat.trove_cat_id),
                          _session_id=self.app.cookies['_session_id'],
                      ))
        user = M.User.query.get(username='test-admin')
        skilldict = dict(category_id=skill_cat._id,
                         comment=comment, level=level)
        assert len(user.skills) == 1 and skilldict in user.skills

        # Add again the same skill
        level = 'medium'
        comment = 'test comment 2'
        self.app.get('/auth/user_info/skills/')
        self.app.post('/auth/user_info/skills/save_skill',
                      params=dict(
                          level=level,
                          comment=comment,
                          selected_skill=str(skill_cat.trove_cat_id),
                          _session_id=self.app.cookies['_session_id'],
                      ))
        user = M.User.query.get(username='test-admin')
        skilldict = dict(category_id=skill_cat._id,
                         comment=comment, level=level)
        assert len(user.skills) == 1 and skilldict in user.skills

        # Add an invalid skill
        level2 = 'not a level'
        comment2 = 'test comment 2'
        self.app.post('/auth/user_info/skills/save_skill',
                      params=dict(
                          level=level2,
                          comment=comment2,
                          selected_skill=str(skill_cat.trove_cat_id),
                          _session_id=self.app.cookies['_session_id'],
                      ))
        user = M.User.query.get(username='test-admin')
        # Check that everything is as it was before
        assert len(user.skills) == 1 and skilldict in user.skills

        # Remove a skill
        self.app.get('/auth/user_info/skills/')
        self.app.post('/auth/user_info/skills/remove_skill',
                      params=dict(
                          categoryid=str(skill_cat.trove_cat_id),
                          _session_id=self.app.cookies['_session_id'],
                      ))
        user = M.User.query.get(username='test-admin')
        assert len(user.skills) == 0

    @td.with_user_project('test-admin')
    def test_user_message(self):
        self.app.get('/').follow()  # establish session
        assert not M.User.query.get(username='test-admin').get_pref('disable_user_messages')
        self.app.post('/auth/preferences/user_message',
                      params={'_session_id': self.app.cookies['_session_id'],
                              })
        assert M.User.query.get(username='test-admin').get_pref('disable_user_messages')
        self.app.post('/auth/preferences/user_message',
                      params={'allow_user_messages': 'on',
                              '_session_id': self.app.cookies['_session_id'],
                              })
        assert not M.User.query.get(username='test-admin').get_pref('disable_user_messages')

    @td.with_user_project('test-admin')
    def test_additional_page(self):
        class MyPP(plugin.UserPreferencesProvider):
            def not_page(self):
                return 'not page'

            @expose()
            def new_page(self):
                return 'new page'

        with mock.patch.object(plugin.UserPreferencesProvider, 'get') as upp_get:
            upp_get.return_value = MyPP()
            r = self.app.get('/auth/new_page')
            assert r.text == 'new page'
            self.app.get('/auth/not_page', status=404)


class TestPasswordReset(TestController):
    test_primary_email = 'testprimaryaddr@mail.com'

    def setup_method(self, method):
        super().setup_method(method)
        # so test-admin isn't automatically logged in for all requests
        self.app.extra_environ = {'disable_auth_magic': 'True'}

    @patch('allura.model.User.send_password_reset_email')
    @patch('allura.lib.plugin.LocalAuthenticationProvider.resend_verification_link')
    @patch('allura.tasks.mail_tasks.sendmail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_email_unconfirmed(self, gen_message_id, sendmail, p_sendlink, p_sendpwd):
        user = M.User.query.get(username='test-admin')
        user.pending = True
        email = M.EmailAddress.find(
            {'claimed_by_user_id': user._id}).first()
        email.confirmed = False
        ThreadLocalORMSession.flush_all()
        self.app.get('/').follow()  # establish session
        self.app.post('/auth/password_recovery_hash', {'email': email.email,
                                                       '_session_id': self.app.cookies['_session_id'],
                                                       })
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        assert hash is None
        p_sendlink.assert_called_once()
        p_sendpwd.assert_not_called()

    @patch('allura.tasks.mail_tasks.sendmail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_user_disabled(self, gen_message_id, sendmail):
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.find(
            {'claimed_by_user_id': user._id}).first()
        user.disabled = True
        ThreadLocalORMSession.flush_all()
        self.app.get('/').follow()  # establish session
        self.app.post('/auth/password_recovery_hash', {'email': email.email,
                                                       '_session_id': self.app.cookies['_session_id'],
                                                       })
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        assert hash is None

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_only_primary_email_reset_allowed(self, gen_message_id, sendmail):
        self.app.get('/').follow()  # establish session
        user = M.User.query.get(username='test-admin')
        user.claim_address(self.test_primary_email)
        user.set_pref('email_address', self.test_primary_email)

        email = M.EmailAddress.find({'email': self.test_primary_email}).first()
        email.confirmed = True
        ThreadLocalORMSession.flush_all()

        with h.push_config(config, **{'auth.allow_non_primary_email_password_reset': 'false'}):
            self.app.post('/auth/password_recovery_hash', {'email': self.test_primary_email,
                                                           '_session_id': self.app.cookies['_session_id'],
                                                           })
            hash = user.get_tool_data('AuthPasswordReset', 'hash')
            assert hash is not None
            args, kwargs = sendmail.post.call_args
            assert kwargs['toaddr'] == self.test_primary_email

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_non_primary_email_reset_allowed(self, gen_message_id, sendmail):
        self.app.get('/').follow()  # establish session
        user = M.User.query.get(username='test-admin')
        email1 = M.EmailAddress.find({'claimed_by_user_id': user._id}).first()
        user.claim_address(self.test_primary_email)
        user.set_pref('email_address', self.test_primary_email)
        email = M.EmailAddress.find({'email': self.test_primary_email}).first()
        email.confirmed = True
        ThreadLocalORMSession.flush_all()
        with h.push_config(config, **{'auth.allow_non_primary_email_password_reset': 'true'}):
            self.app.post('/auth/password_recovery_hash', {'email': email1.email,
                                                           '_session_id': self.app.cookies['_session_id'],
                                                           })
            hash = user.get_tool_data('AuthPasswordReset', 'hash')
            assert hash is not None
            args, kwargs = sendmail.post.call_args
            assert kwargs['toaddr'] == email1.email

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_password_reset(self, gen_message_id, sendsimplemail):
        self.app.get('/').follow()  # establish session
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.find({'claimed_by_user_id': user._id}).first()
        email.confirmed = True
        ThreadLocalORMSession.flush_all()
        old_pw_hash = user.password

        # request a reset
        with td.audits('Password recovery link sent to: ' + email.email, user=True):
            r = self.app.post('/auth/password_recovery_hash', {'email': email.email,
                                                               '_session_id': self.app.cookies['_session_id'],
                                                               })
        # confirm some fields
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        hash_expiry = user.get_tool_data('AuthPasswordReset', 'hash_expiry')
        assert hash is not None
        assert hash_expiry is not None

        # confirm email sent
        text = '''Your username is test-admin

To update your password on %s, please visit the following URL:

%s/auth/forgotten_password/%s''' % (config['site_name'], config['base_url'], hash)
        sendsimplemail.post.assert_called_once_with(
            sender='noreply@localhost',
            toaddr=email.email,
            fromaddr='"{}" <{}>'.format(config['site_name'], config['forgemail.return_path']),
            reply_to=config['forgemail.return_path'],
            subject='Allura Password recovery',
            message_id=gen_message_id(),
            text=text)

        # load reset form and fill it out
        r = self.app.get('/auth/forgotten_password/%s' % hash)
        assert 'Enter a new password for: test-admin' in r
        assert 'New Password:' in r
        assert 'New Password (again):' in r
        form = r.forms[0]
        form['pw'] = form['pw2'] = new_password = '154321'
        with td.audits(r'Password changed \(through recovery process\)', user=True):
            # escape parentheses, so they would not be treated as regex group
            r = form.submit()

        # verify 'Password Changed' email sent
        args, kwargs = sendsimplemail.post.call_args
        assert kwargs['toaddr'] == user._id
        assert kwargs['subject'] == 'Password Changed'

        # confirm password changed and works
        user = M.User.query.get(username='test-admin')
        assert old_pw_hash != user.password
        provider = plugin.LocalAuthenticationProvider(None)
        assert provider._validate_password(user, new_password)

        # confirm reset fields cleared
        user = M.User.query.get(username='test-admin')
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        hash_expiry = user.get_tool_data('AuthPasswordReset', 'hash_expiry')
        assert hash == ''
        assert hash_expiry == ''

        # confirm can log in now in same session
        r = r.follow()
        assert 'Log Out' not in r, r
        form = r.forms[0]
        encoded = self.app.antispam_field_names(r.form)
        form[encoded['username']] = 'test-admin'
        form[encoded['password']] = new_password
        r = form.submit(status=302)
        r = r.follow().follow()
        assert 'Log Out' in r, r

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_hash_expired(self, gen_message_id, sendmail):
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.find(
            {'claimed_by_user_id': user._id}).first()
        email.confirmed = True
        ThreadLocalORMSession.flush_all()
        self.app.get('/').follow()  # establish session
        r = self.app.post('/auth/password_recovery_hash', {'email': email.email,
                                                           '_session_id': self.app.cookies['_session_id'],
                                                           })
        user = M.User.by_username('test-admin')
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        user.set_tool_data('AuthPasswordReset',
                           hash_expiry=datetime(2000, 10, 10))
        r = self.app.get('/auth/forgotten_password/%s' % hash.encode('utf-8'))
        assert 'Unable to process reset, please try again' in r.follow().text
        r = self.app.post('/auth/set_new_password/%s' %
                          hash.encode('utf-8'), {'pw': '154321', 'pw2': '154321',
                                                 '_session_id': self.app.cookies['_session_id'],
                                                 })
        assert 'Unable to process reset, please try again' in r.follow().text

    def test_hash_invalid(self):
        r = self.app.get('/auth/forgotten_password/123412341234', status=302)
        assert 'Unable to process reset, please try again' in r.follow().text

    @patch('allura.lib.plugin.AuthenticationProvider')
    def test_provider_disabled(self, AP):
        user = M.User.query.get(username='test-admin')
        ap = AP.get()
        ap.forgotten_password_process = False
        ap.authenticate_request()._id = user._id
        ap.by_username().username = user.username
        self.app.get('/auth/forgotten_password', status=404)
        self.app.get('/').follow()  # establish session
        self.app.post('/auth/set_new_password',
                      {'pw': 'foo', 'pw2': 'foo', '_session_id': self.app.cookies['_session_id']},
                      status=404)
        self.app.post('/auth/password_recovery_hash',
                      {'email': 'foo', '_session_id': self.app.cookies['_session_id']},
                      status=404)

    @patch('allura.lib.plugin.AuthenticationProvider.hibp_password_check_enabled', Mock(return_value=True))
    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_pwd_reset_hibp_check(self, gen_message_id, sendmail):
        self.app.get('/').follow()  # establish session
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.find({'claimed_by_user_id': user._id}).first()
        email.confirmed = True
        ThreadLocalORMSession.flush_all()

        # request a reset
        r = self.app.post('/auth/password_recovery_hash', {'email': email.email,
                                                           '_session_id': self.app.cookies['_session_id'],
                                                           })
        hash = user.get_tool_data('AuthPasswordReset', 'hash')

        # load reset form and fill it out with weak password
        r = self.app.get('/auth/forgotten_password/%s' % hash)
        form = r.forms[0]
        form['pw'] = form['pw2'] = new_password = 'password'
        r = form.submit()
        assert 'Unsafe' in str(r.headers)

        # fill it out again, with a stronger password
        r = r.follow()
        form = r.forms[0]
        form['pw'] = form['pw2'] = new_password = 'oj35h9u34280j924hnuiw'  # something unlikely to trip at hibp
        r = form.submit()
        assert 'Unsafe' not in str(r.headers)

        # confirm password changed and works
        user = M.User.query.get(username='test-admin')
        provider = plugin.LocalAuthenticationProvider(None)
        assert provider._validate_password(user, new_password)

        # confirm can log in now in same session
        r = r.follow()
        assert 'Log Out' not in r, r
        form = r.forms[0]
        encoded = self.app.antispam_field_names(r.form)
        form[encoded['username']] = 'test-admin'
        form[encoded['password']] = new_password
        r = form.submit(status=302)
        r = r.follow().follow()
        assert 'Log Out' in r, r


class TestOAuth(TestController):
    def test_register_deregister_app(self):
        # register
        r = self.app.get('/auth/oauth/')
        r = self.app.post('/auth/oauth/register',
                          params={'application_name': 'oautstapp', 'application_description': 'Oauth rulez',
                                  '_session_id': self.app.cookies['_session_id'],
                                  }).follow()
        assert 'oautstapp' in r
        # deregister
        assert r.forms[0].action == 'deregister'
        r.forms[0].submit()
        r = self.app.get('/auth/oauth/')
        assert 'oautstapp' not in r

    def test_generate_revoke_access_token(self):
        # generate
        self.app.get('/').follow()  # establish session
        r = self.app.post('/auth/oauth/register',
                          params={'application_name': 'oautstapp', 'application_description': 'Oauth rulez',
                                  '_session_id': self.app.cookies['_session_id'],
                                  }, status=302)
        r = self.app.get('/auth/oauth/')
        assert r.forms[1].action == 'generate_access_token'
        r = r.forms[1].submit(extra_environ={'username': 'test-user'})  # not the right user
        assert "Invalid app ID" in self.webflash(r)                   # gets an error
        r = self.app.get('/auth/oauth/')                                # do it again
        r = r.forms[1].submit()                                         # as correct user
        assert '' == self.webflash(r)

        r = self.app.get('/auth/oauth/')
        assert 'Bearer Token:' in r
        assert (
            M.OAuthAccessToken.for_user(M.User.by_username('test-admin')) != [])
        # revoke
        assert r.forms[0].action == 'revoke_access_token'
        r.forms[0].submit()
        r = self.app.get('/auth/oauth/')
        assert r.forms[0].action != 'revoke_access_token'
        assert (
            M.OAuthAccessToken.for_user(M.User.by_username('test-admin')) == [])

    def test_interactive(self):
        user = M.User.by_username('test-admin')
        M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            secret_key='test-client-secret',
            user_id=user._id,
            description='ctok_desc',
        )
        ThreadLocalORMSession.flush_all()
        oauth_params = dict(
            client_key='api_key_api_key_12345',
            client_secret='test-client-secret',
            callback_uri='http://my.domain.com/callback',
        )
        r = self.app.post(*oauth1_webtest('/rest/oauth/request_token', oauth_params, method='POST'))
        rtok = parse_qs(r.text)['oauth_token'][0]
        rsecr = parse_qs(r.text)['oauth_token_secret'][0]
        assert rtok
        assert rsecr
        r = self.app.post('/rest/oauth/authorize',
                          params={'oauth_token': rtok})
        r = r.forms[0].submit('yes')
        assert r.location.startswith('http://my.domain.com/callback')
        pin = parse_qs(urlparse(r.location).query)['oauth_verifier'][0]
        assert pin

        oauth_params = dict(
            client_key='api_key_api_key_12345',
            client_secret='test-client-secret',
            resource_owner_key=rtok,
            resource_owner_secret=rsecr,
            verifier=pin,
        )
        r = self.app.get(*oauth1_webtest('/rest/oauth/access_token', oauth_params))
        atok = parse_qs(r.text)
        assert len(atok['oauth_token']) == 1
        assert len(atok['oauth_token_secret']) == 1

        # now use the tokens & secrets to make a full OAuth request:
        oauth_token = atok['oauth_token'][0]
        oauth_secret = atok['oauth_token_secret'][0]
        oaurl, oaparams, oahdrs, oaextraenv = oauth1_webtest('/rest/p/test/', dict(
            client_key='api_key_api_key_12345',
            client_secret='test-client-secret',
            resource_owner_key=oauth_token,
            resource_owner_secret=oauth_secret,
            signature_type='query'
        ))
        resp = self.app.get(oaurl, oaparams, oahdrs, oaextraenv, status=200)
        for tool in resp.json['tools']:
            if tool['name'] == 'admin':
                break  # good, found Admin
        else:
            raise AssertionError(f"No 'admin' tool in response, maybe authorizing as correct user failed. {resp.json}")

        # definitely bad request
        self.app.get(oaurl.replace('oauth_signature=', 'removed='), oaparams, oahdrs, oaextraenv, status=401)

    def test_authorize_ok(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key_reqtok_12345',
            consumer_token_id=ctok._id,
            callback='oob',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/authorize', params={'oauth_token': 'api_key_reqtok_12345'})
        assert 'ctok_desc' in r.text
        assert 'api_key_reqtok_12345' in r.text

    def test_authorize_invalid(self):
        resp = self.app.post('/rest/oauth/authorize', params={'oauth_token': 'api_key_reqtok_12345'}, status=400)
        resp.mustcontain('error=invalid_client')

    def test_do_authorize_no(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key_reqtok_12345',
            consumer_token_id=ctok._id,
            callback='oob',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        self.app.post('/rest/oauth/do_authorize',
                      params={'no': '1', 'oauth_token': 'api_key_reqtok_12345'})
        assert M.OAuthRequestToken.query.get(api_key='api_key_reqtok_12345') is None

    def test_do_authorize_oob(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key_reqtok_12345',
            consumer_token_id=ctok._id,
            callback='oob',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/do_authorize', params={'yes': '1', 'oauth_token': 'api_key_reqtok_12345'})
        assert r.html.find(text=re.compile('^PIN: ')) is not None

    def test_do_authorize_cb(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key_reqtok_12345',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/do_authorize', params={'yes': '1', 'oauth_token': 'api_key_reqtok_12345'})
        assert r.location.startswith('http://my.domain.com/callback?oauth_token=api_key_reqtok_12345&oauth_verifier=')

    def test_do_authorize_cb_params(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key_reqtok_12345',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/do_authorize', params={'yes': '1', 'oauth_token': 'api_key_reqtok_12345'})
        assert r.location.startswith('http://my.domain.com/callback?myparam=foo&oauth_token=api_key_reqtok_12345&oauth_verifier=')


class TestOAuthRequestToken(TestController):

    oauth_params = dict(
        client_key='api_key_api_key_12345',
        client_secret='test-client-secret',
    )

    def setup_method(self, method):
        super().setup_method(method)
        dummy_oauths()

    def test_request_token_valid(self):
        user = M.User.by_username('test-user')
        consumer_token = M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            secret_key='test-client-secret',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post(*oauth1_webtest('/rest/oauth/request_token', self.oauth_params, method='POST'))
        r.mustcontain('oauth_token=')
        r.mustcontain('oauth_token_secret=')
        request_token = M.OAuthRequestToken.query.get(consumer_token_id=consumer_token._id)
        assert request_token is not None

    def test_request_token_no_consumer_token_matching(self):
        self.app.post(*oauth1_webtest('/rest/oauth/request_token', self.oauth_params), status=401)

    def test_request_token_no_consumer_token_given(self):
        oauth_params = self.oauth_params.copy()
        oauth_params['signature_type'] = 'query'  # so we can more easily remove a param next
        url, params, hdrs, extraenv = oauth1_webtest('/rest/oauth/request_token', oauth_params)
        url = url.replace('oauth_consumer_key', 'gone')
        resp = self.app.post(url, params, hdrs, extraenv, status=400)
        resp.mustcontain('error_description=Missing+mandatory+OAuth+parameters')

    def test_request_token_invalid(self):
        user = M.User.by_username('test-user')
        M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            user_id=user._id,
            secret_key='test-client-secret--INVALID',
        )
        ThreadLocalORMSession.flush_all()
        self.app.post(*oauth1_webtest('/rest/oauth/request_token', self.oauth_params, method='POST'),
                      status=401)


class TestOAuthAccessToken(TestController):

    oauth_params = dict(
        client_key='api_key_api_key_12345',
        client_secret='test-client-secret',
        resource_owner_key='api_key_reqtok_12345',
        resource_owner_secret='test-token-secret',
        verifier='good_verifier_123456',
    )

    def setup_method(self, method):
        super().setup_method(method)
        dummy_oauths()

    def test_access_token_no_consumer(self):
        self.app.get(*oauth1_webtest('/rest/oauth/access_token', self.oauth_params), status=401)

    def test_access_token_no_request(self):
        user = M.User.by_username('test-admin')
        M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            user_id=user._id,
            description='ctok_desc',
        )
        ThreadLocalORMSession.flush_all()
        self.app.get(*oauth1_webtest('/rest/oauth/access_token', self.oauth_params), status=401)

    def test_access_token_bad_pin(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key_reqtok_12345',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
            validation_pin='good_verifier_123456',
        )
        ThreadLocalORMSession.flush_all()
        oauth_params = self.oauth_params.copy()
        oauth_params['verifier'] = 'bad_verifier_1234567'
        self.app.get(*oauth1_webtest('/rest/oauth/access_token', oauth_params),
                     status=401)

    def test_access_token_bad_sig(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            user_id=user._id,
            description='ctok_desc',
            secret_key='test-client-secret',
        )
        M.OAuthRequestToken(
            api_key='api_key_reqtok_12345',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
            validation_pin='good_verifier_123456',
            secret_key='test-token-secret--INVALID',
        )
        ThreadLocalORMSession.flush_all()
        self.app.get(*oauth1_webtest('/rest/oauth/access_token', self.oauth_params), status=401)

    def test_access_token_ok(self, signature_type='auth_header'):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key_api_key_12345',
            secret_key='test-client-secret',
            user_id=user._id,
            description='ctok_desc',
        )
        req_tok = M.OAuthRequestToken(
            api_key='api_key_reqtok_12345',
            secret_key='test-token-secret',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
            validation_pin='good_verifier_123456',
        )
        ThreadLocalORMSession.flush_all()

        oauth_params = dict(self.oauth_params, signature_type=signature_type)
        r = self.app.get(*oauth1_webtest('/rest/oauth/access_token', self.oauth_params))
        atok = parse_qs(r.text)
        assert len(atok['oauth_token']) == 1
        assert len(atok['oauth_token_secret']) == 1

    def test_access_token_ok_by_query(self):
        self.test_access_token_ok(signature_type='query')


class TestDisableAccount(TestController):
    def test_not_authenticated(self):
        r = self.app.get(
            '/auth/disable/',
            extra_environ={'username': '*anonymous'})
        assert r.status_int == 302
        assert (r.location ==
                     'http://localhost/auth/?return_to=%2Fauth%2Fdisable%2F')

    def test_lists_user_projects(self):
        r = self.app.get('/auth/disable/')
        user = M.User.by_username('test-admin')
        for p in user.my_projects_by_role_name('Admin'):
            if p.name == 'u/test-admin':
                continue
            assert p.name in r
            assert p.url() in r

    def test_has_asks_password(self):
        r = self.app.get('/auth/disable/')
        form = r.html.find('form', {'action': 'do_disable'})
        assert form is not None

    def test_bad_password(self):
        self.app.get('/').follow()  # establish session
        r = self.app.post('/auth/disable/do_disable', {'password': 'bad',
                                                       '_session_id': self.app.cookies['_session_id'], })
        assert 'Invalid password' in r
        user = M.User.by_username('test-admin')
        assert user.disabled is False

    def test_disable(self):
        self.app.get('/').follow()  # establish session
        r = self.app.post('/auth/disable/do_disable', {'password': 'foo',
                                                       '_session_id': self.app.cookies['_session_id'], })
        assert r.status_int == 302
        assert r.location == 'http://localhost/'
        flash = json.loads(self.webflash(r))
        assert flash['status'] == 'ok'
        assert flash['message'] == 'Your account was successfully disabled!'
        user = M.User.by_username('test-admin')
        assert user.disabled is True


class TestPasswordExpire(TestController):
    def login(self, username='test-user', pwd='foo', query_string=''):
        extra = {'username': '*anonymous', 'REMOTE_ADDR': '127.0.0.1'}
        r = self.app.get('/auth/' + query_string, extra_environ=extra)

        f = r.forms[0]
        encoded = self.app.antispam_field_names(f)
        f[encoded['username']] = username
        f[encoded['password']] = pwd
        return f.submit(extra_environ={'username': '*anonymous'})

    def assert_redirects(self, where='/'):
        resp = self.app.get(where, extra_environ={'username': 'test-user'}, status=302)
        assert resp.location == 'http://localhost/auth/pwd_expired?' + urlencode({'return_to': where})

    def assert_not_redirects(self, where='/neighborhood'):
        self.app.get(where, extra_environ={'username': 'test-user'}, status=200)

    def test_disabled(self):
        r = self.login()
        assert not r.session.get('pwd-expired')
        self.assert_not_redirects()

    def expired(self, r):
        return r.session.get('pwd-expired')

    def set_expire_for_user(self, username='test-user', days=100):
        user = M.User.by_username(username)
        user.last_password_updated = datetime.utcnow() - timedelta(days=days)
        session(user).flush(user)
        return user

    def test_days(self):
        self.set_expire_for_user()

        with h.push_config(config, **{'auth.pwdexpire.days': 180}):
            r = self.login()
            assert not self.expired(r)
            self.assert_not_redirects()

        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login()
            assert self.expired(r)
            self.assert_redirects()

    def test_before(self):
        self.set_expire_for_user()

        before = datetime.utcnow() - timedelta(days=180)
        before = calendar.timegm(before.timetuple())
        with h.push_config(config, **{'auth.pwdexpire.before': before}):
            r = self.login()
            assert not self.expired(r)
            self.assert_not_redirects()

        before = datetime.utcnow() - timedelta(days=90)
        before = calendar.timegm(before.timetuple())
        with h.push_config(config, **{'auth.pwdexpire.before': before}):
            r = self.login()
            assert self.expired(r)
            self.assert_redirects()

    def test_logout(self):
        self.set_expire_for_user()
        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login()
            assert self.expired(r)
            self.assert_redirects()
            r = self.app.get('/auth/logout', extra_environ={'username': 'test-user'})
            assert not self.expired(r)
            self.assert_not_redirects()

    def test_change_pwd(self):
        self.set_expire_for_user()
        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login()
            assert self.expired(r)
            self.assert_redirects()

            user = M.User.by_username('test-user')
            old_update_time = user.last_password_updated
            old_password = user.password
            r = self.app.get('/auth/pwd_expired', extra_environ={'username': 'test-user'})
            f = r.forms[0]
            f['oldpw'] = 'foo'
            f['pw'] = 'qwerty'
            f['pw2'] = 'qwerty'
            r = f.submit(extra_environ={'username': 'test-user'}, status=302)
            assert r.location == 'http://localhost/'
            assert not self.expired(r)
            user = M.User.by_username('test-user')
            assert user.last_password_updated > old_update_time
            assert user.password != old_password

            # Can log in with new password and change isn't required anymore
            r = self.login(pwd='qwerty').follow()
            assert r.location == 'http://localhost/dashboard'
            assert 'Invalid login' not in r
            assert not self.expired(r)
            self.assert_not_redirects()

            # and can't log in with old password
            r = self.login(pwd='foo')
            assert 'Invalid login' in r

    def test_expired_pwd_change_invalidates_token(self):
        self.set_expire_for_user()
        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login()
            assert self.expired(r)
            self.assert_redirects()
            user = M.User.by_username('test-user')
            user.set_tool_data('AuthPasswordReset',
                               hash="generated_hash_value",
                               hash_expiry="04-08-2020")
            hash = user.get_tool_data('AuthPasswordReset', 'hash')
            hash_expiry = user.get_tool_data('AuthPasswordReset', 'hash_expiry')
            assert hash == 'generated_hash_value'
            assert hash_expiry == '04-08-2020'
            session(user).flush(user)

            # Change expired password
            r = self.app.get('/auth/pwd_expired', extra_environ={'username': 'test-user'})
            f = r.forms[0]
            f['oldpw'] = 'foo'
            f['pw'] = 'qwerty'
            f['pw2'] = 'qwerty'
            r = f.submit(extra_environ={'username': 'test-user'}, status=302)
            assert r.location == 'http://localhost/'

            user = M.User.by_username('test-user')
            hash = user.get_tool_data('AuthPasswordReset', 'hash')
            hash_expiry = user.get_tool_data('AuthPasswordReset', 'hash_expiry')

            assert hash == ''
            assert hash_expiry == ''

    def check_validation(self, oldpw, pw, pw2):
        user = M.User.by_username('test-user')
        old_update_time = user.last_password_updated
        old_password = user.password
        r = self.app.get('/auth/pwd_expired', extra_environ={'username': 'test-user'})
        f = r.forms[0]
        f['oldpw'] = oldpw
        f['pw'] = pw
        f['pw2'] = pw2
        r = f.submit(extra_environ={'username': 'test-user'})
        assert self.expired(r)
        user = M.User.by_username('test-user')
        assert user.last_password_updated == old_update_time
        assert user.password == old_password
        return r

    def test_change_pwd_validation(self):
        self.set_expire_for_user()
        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login()
            assert self.expired(r)
            self.assert_redirects()

            r = self.check_validation('', '', '')
            assert 'Please enter a value' in r
            r = self.check_validation('', 'qwe', 'qwerty')
            assert 'Enter a value 6 characters long or more' in r
            r = self.check_validation('bad', 'qwerty1', 'qwerty')
            assert 'Passwords must match' in r
            r = self.check_validation('bad', 'qwerty', 'qwerty')
            assert 'Incorrect password' in self.webflash(r)
            assert r.location == 'http://localhost/auth/pwd_expired?return_to='

            with h.push_config(config, **{'auth.min_password_len': 3}):
                r = self.check_validation('foo', 'foo', 'foo')
                assert 'Your old and new password should not be the same' in r

    def test_return_to(self):
        return_to = '/p/test/tickets/?milestone=1.0&page=2'
        self.set_expire_for_user()
        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login(query_string='?' + urlencode({'return_to': return_to}))
            # don't go to the return_to yet
            assert r.location == 'http://localhost/auth/pwd_expired?' + urlencode({'return_to': return_to})

            # but if user tries to go directly there anyway, intercept and redirect back
            self.assert_redirects(where=return_to)

            r = self.app.get('/auth/pwd_expired', extra_environ={'username': 'test-user'})
            f = r.forms[0]
            f['oldpw'] = 'foo'
            f['pw'] = 'qwerty'
            f['pw2'] = 'qwerty'
            f['return_to'] = return_to
            r = f.submit(extra_environ={'username': 'test-user'}, status=302)
            assert r.location == 'http://localhost/p/test/tickets/?milestone=1.0&page=2'


class TestCSRFProtection(TestController):
    def test_blocks_invalid(self):
        # so test-admin isn't automatically logged in for all requests
        self.app.extra_environ = {'disable_auth_magic': 'True', 'REMOTE_ADDR': '127.0.0.1'}

        # regular login
        r = self.app.get('/auth/')

        r = self.app.post('/auth/do_login', params=dict(
            username='test-admin', password='foo',
            _session_id=self.app.cookies['_session_id']),
            antispam=True)

        # regular form submit
        r = self.app.get('/admin/overview')
        r = r.form.submit()
        assert r.location == 'http://localhost/admin/overview'

        # invalid form submit
        r = self.app.get('/admin/overview')
        r.form['_session_id'] = 'bogus'
        r = r.form.submit()
        assert r.location == 'http://localhost/auth/'

    def test_blocks_invalid_on_login(self):
        r = self.app.get('/auth/')
        r.form['_session_id'] = 'bogus'
        r.form.submit(status=403)

    def test_token_present_on_first_request(self):
        r = self.app.get('/auth/')
        assert r.form['_session_id'].value


class TestTwoFactor(TestController):

    sample_key = b'\x00K\xda\xbfv\xc2B\xaa\x1a\xbe\xa5\x96b\xb2\xa0Z:\xc9\xcf\x8a'
    sample_b32 = 'ABF5VP3WYJBKUGV6UWLGFMVALI5MTT4K'

    def _init_totp(self, username='test-admin'):
        user = M.User.query.get(username=username)
        totp_srv = TotpService().get()
        totp_srv.set_secret_key(user, self.sample_key)
        user.set_pref('multifactor', True)

    def test_settings_on(self):
        r = self.app.get('/auth/preferences/')
        assert r.html.find(attrs={'class': 'preferences multifactor'})

    def test_settings_off(self):
        with h.push_config(config, **{'auth.multifactor.totp': 'false'}):
            r = self.app.get('/auth/preferences/')
            assert not r.html.find(attrs={'class': 'preferences multifactor'})

            for url in ['/auth/preferences/totp_new',
                        '/auth/preferences/totp_view',
                        '/auth/preferences/totp_set',
                        '/auth/preferences/totp_send_link',
                        '/auth/preferences/multifactor_disable',
                        '/auth/preferences/multifactor_recovery',
                        '/auth/preferences/multifactor_recovery_regen',
                        '/auth/multifactor',
                        '/auth/do_multifactor',
                        ]:
                self.app.post(url,
                              {'password': 'foo', '_session_id': self.app.cookies['_session_id']},
                              status=404)

    def test_user_disabled(self):
        r = self.app.get('/auth/preferences/')
        info_html = str(r.html.find(attrs={'class': 'preferences multifactor'}))
        assert 'disabled' in info_html

    def test_user_enabled(self):
        self._init_totp()
        r = self.app.get('/auth/preferences/')
        info_html = str(r.html.find(attrs={'class': 'preferences multifactor'}))
        assert 'enabled' in info_html

    def test_reconfirm_auth(self):
        from datetime import datetime as real_datetime
        with patch('allura.lib.decorators.datetime') as datetime:
            datetime.min = real_datetime.min

            # reconfirm required at first
            datetime.utcnow.return_value = real_datetime(2016, 1, 1, 0, 0, 0)
            r = self.app.get('/auth/preferences/totp_new')
            assert 'Password Confirmation' in r

            # submit form, and its not required
            r.form['password'] = 'foo'
            r = r.form.submit()
            assert 'Password Confirmation' not in r

            # still not required
            datetime.utcnow.return_value = real_datetime(2016, 1, 1, 0, 1, 45)
            r = self.app.get('/auth/preferences/totp_new')
            assert 'Password Confirmation' not in r

            # required later
            datetime.utcnow.return_value = real_datetime(2016, 1, 1, 0, 2, 3)
            r = self.app.get('/auth/preferences/totp_new')
            assert 'Password Confirmation' in r

    def test_enable_totp(self):
        # create a separate session, for later use in the test
        other_session = TestController()
        other_session.setup_method(None)
        other_session.app.get('/auth/preferences/')

        with out_audits(user=True):
            r = self.app.get('/auth/preferences/totp_new')
            assert 'Password Confirmation' in r

        with audits('Visited multifactor new TOTP page', user=True):
            r.form['password'] = 'foo'
            r = r.form.submit()
            assert 'Scan this' in r
            assert 'Or enter setup key: ' in r

        first_key_shown = r.session['totp_new_key']

        with audits(r'Failed to set up multifactor TOTP \(wrong code\)', user=True):
            form = r.forms['totp_set']
            form['code'] = ''
            r = form.submit()
            assert 'Invalid' in r
            assert f'Or enter setup key: {b32encode(first_key_shown).decode()}' in r
            assert first_key_shown == r.session['totp_new_key']  # different keys on each pageload would be bad!

        new_totp = TotpService().Totp(r.session['totp_new_key'])
        code = new_totp.generate(time_time())
        form = r.forms['totp_set']
        form['code'] = code
        with audits('Set up multifactor TOTP', user=True):
            r = form.submit()
            assert 'Two factor authentication has now been set up.' == json.loads(self.webflash(r))['message'], self.webflash(r)

        tasks = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendsimplemail')).all()
        assert len(tasks) == 1
        assert tasks[0].kwargs['subject'] == 'Two-Factor Authentication Enabled'
        assert 'new two-factor authentication' in tasks[0].kwargs['text']

        r = r.follow()
        assert 'Recovery Codes' in r

        # Confirm any pre-existing sessions have to re-authenticate
        r = other_session.app.get('/auth/preferences/')
        assert '/auth/?return_to' in r.headers['Location']
        other_session.teardown_method(None)

    def test_reset_totp(self):
        self._init_totp()

        # access page
        r = self.app.get('/auth/preferences/totp_new')
        assert 'Password Confirmation' in r

        # reconfirm password to get to it
        r.form['password'] = 'foo'
        r = r.form.submit()

        # confirm warning message, and key is not changed yet
        assert 'Scan this' in r
        assert 'Or enter setup key: ' in r
        assert 'this will invalidate your previous' in r
        current_key = TotpService.get().get_secret_key(M.User.query.get(username='test-admin'))
        assert self.sample_key == current_key

        # incorrect submission
        form = r.forms['totp_set']
        form['code'] = ''
        r = form.submit()
        assert 'Invalid' in r

        # still unchanged key
        current_key = TotpService.get().get_secret_key(M.User.query.get(username='test-admin'))
        assert self.sample_key == current_key

        # valid submission
        new_key = r.session['totp_new_key']
        new_totp = TotpService().Totp(new_key)
        code = new_totp.generate(time_time())
        form = r.forms['totp_set']
        form['code'] = code
        r = form.submit()
        assert 'Two factor authentication has now been set up.' == json.loads(self.webflash(r))['message'], self.webflash(r)

        # new key in place
        current_key = TotpService.get().get_secret_key(M.User.query.get(username='test-admin'))
        assert new_key == current_key
        assert self.sample_key != current_key

    def test_disable(self):
        self._init_totp()

        self.app.get('/auth/preferences/multifactor_disable', status=405)  # GET not allowed

        # get form and submit
        r = self.app.get('/auth/preferences/')
        form = r.forms['multifactor_disable']
        r = form.submit()

        # confirm first, no change
        assert 'Password Confirmation' in r
        user = M.User.query.get(username='test-admin')
        assert user.get_pref('multifactor') is True

        # confirm submit, everything goes off
        r.form['password'] = 'foo'
        with audits('Disabled multifactor TOTP', user=True):
            r = r.form.submit()
            assert 'Multifactor authentication has now been disabled.' == json.loads(self.webflash(r))['message'], self.webflash(r)
        user = M.User.query.get(username='test-admin')
        assert user.get_pref('multifactor') is False
        assert TotpService().get().get_secret_key(user) is None
        assert RecoveryCodeService().get().get_codes(user) == []

        # email confirmation
        tasks = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendsimplemail')).all()
        assert len(tasks) == 1
        assert tasks[0].kwargs['subject'] == 'Two-Factor Authentication Disabled'
        assert 'disabled two-factor authentication' in tasks[0].kwargs['text']

    def test_login_totp(self):
        self._init_totp()

        # so test-admin isn't automatically logged in for all requests
        self.app.extra_environ = {'disable_auth_magic': 'True'}

        # regular login
        r = self.app.get('/auth/?return_to=/p/foo')
        encoded = self.app.antispam_field_names(r.form)
        r.form[encoded['username']] = 'test-admin'
        r.form[encoded['password']] = 'foo'
        with audits('Multifactor login - password ok, code not entered yet', user=True):
            r = r.form.submit()

        # check results
        assert r.location.endswith('/auth/multifactor?return_to=%2Fp%2Ffoo'), r
        r = r.follow()
        assert not r.session.get('username')

        # try an invalid code
        r.form['code'] = 'invalid-code'
        with audits('Multifactor login - invalid code', user=True):
            r = r.form.submit()
        assert 'Invalid code' in r
        assert not r.session.get('username')

        # use a valid code
        totp = TotpService().Totp(self.sample_key)
        code = totp.generate(time_time())
        r.form['code'] = code
        with audits('Successful login', user=True):
            r = r.form.submit()

        # confirm login and final page
        assert r.session['username'] == 'test-admin'
        assert r.location.endswith('/p/foo'), r

    def test_login_rate_limit(self):
        self._init_totp()

        # so test-admin isn't automatically logged in for all requests
        self.app.extra_environ = {'disable_auth_magic': 'True'}

        # regular login
        r = self.app.get('/auth/?return_to=/p/foo')
        encoded = self.app.antispam_field_names(r.form)

        r.form[encoded['username']] = 'test-admin'
        r.form[encoded['password']] = 'foo'
        r = r.form.submit()
        r = r.follow()

        # try some invalid codes
        for i in range(3):
            r.form['code'] = 'invalid-code'
            r = r.form.submit()
            assert 'Invalid code' in r

        # use a valid code, but it'll hit rate limit
        totp = TotpService().Totp(self.sample_key)
        code = totp.generate(time_time())
        r.form['code'] = code
        with audits('Multifactor login - rate limit', user=True):
            r = r.form.submit()

        assert 'rate limit exceeded' in r
        assert not r.session.get('username')

    def test_login_totp_disrupted(self):
        self._init_totp()

        # so test-admin isn't automatically logged in for all requests
        self.app.extra_environ = {'disable_auth_magic': 'True'}

        # regular login
        r = self.app.get('/auth/')
        encoded = self.app.antispam_field_names(r.form)
        r.form[encoded['username']] = 'test-admin'
        r.form[encoded['password']] = 'foo'
        r = r.form.submit()
        r = r.follow()

        # go to some other page instead of filling out the 2FA code
        other_r = self.app.get('/')

        # then try to complete the 2FA form
        totp = TotpService().Totp(self.sample_key)
        code = totp.generate(time_time())
        r.form['code'] = code
        r = r.form.submit()

        # sent back to regular login
        assert ('Your multifactor login was disrupted, please start over.' ==
                     json.loads(self.webflash(r))['message']), self.webflash(r)
        r = r.follow()
        assert 'Password Login' in r

    def test_login_recovery_code(self):
        self._init_totp()

        # so test-admin isn't automatically logged in for all requests
        self.app.extra_environ = {'disable_auth_magic': 'True'}

        # regular login
        r = self.app.get('/auth/?return_to=/p/foo')
        encoded = self.app.antispam_field_names(r.form)
        r.form[encoded['username']] = 'test-admin'
        r.form[encoded['password']] = 'foo'
        r = r.form.submit()

        # check results
        assert r.location.endswith('/auth/multifactor?return_to=%2Fp%2Ffoo'), r
        r = r.follow()
        assert not r.session.get('username')

        # change login mode
        r.form['mode'] = 'recovery'

        # try an invalid code
        r.form['code'] = 'invalid-code'
        r = r.form.submit()
        assert 'Invalid code' in r
        assert not r.session.get('username')

        # use a valid code
        user = M.User.by_username('test-admin')
        recovery = RecoveryCodeService().get()
        recovery.regenerate_codes(user)
        recovery_code = recovery.get_codes(user)[0]
        r.form['code'] = recovery_code
        with audits('Logged in using a multifactor recovery code', user=True):
            r = r.form.submit()

        # confirm login and final page
        assert r.session['username'] == 'test-admin'
        assert r.location.endswith('/p/foo'), r

        # confirm code used up
        assert recovery_code not in RecoveryCodeService().get().get_codes(user)

    @patch('allura.lib.plugin.AuthenticationProvider.hibp_password_check_enabled', Mock(return_value=True))
    def test_login_totp_with_hibp(self):
        # this is essentially the same as regular TOTP test, just making sure that HIBP doesn't get in the way
        # or cause any problems.  It shouldn't even run since a password isn't present when the final login happens

        self._init_totp()

        # so test-admin isn't automatically logged in for all requests
        self.app.extra_environ = {'disable_auth_magic': 'True'}

        # regular login
        r = self.app.get('/auth/?return_to=/p/foo')
        encoded = self.app.antispam_field_names(r.form)
        r.form[encoded['username']] = 'test-admin'
        r.form[encoded['password']] = 'foo'
        with audits('Multifactor login - password ok, code not entered yet', user=True):
            r = r.form.submit()

        # check results
        assert r.location.endswith('/auth/multifactor?return_to=%2Fp%2Ffoo'), r
        r = r.follow()
        assert not r.session.get('username')

        # use a valid code
        totp = TotpService().Totp(self.sample_key)
        code = totp.generate(time_time())
        r.form['code'] = code
        with audits('Successful login', user=True):
            r = r.form.submit()

        # confirm login and final page
        assert r.session['username'] == 'test-admin'
        assert r.location.endswith('/p/foo'), r

    def test_view_key(self):
        self._init_totp()

        with out_audits(user=True):
            r = self.app.get('/auth/preferences/totp_view')
            assert 'Password Confirmation' in r

        with audits('Viewed multifactor TOTP config page', user=True):
            r.form['password'] = 'foo'
            r = r.form.submit()
            assert 'Scan this' in r
            assert f'Or enter setup key: {self.sample_b32}' in r

    def test_view_recovery_codes_and_regen(self):
        self._init_totp()

        # reconfirm password
        with out_audits(user=True):
            r = self.app.get('/auth/preferences/multifactor_recovery')
            assert 'Password Confirmation' in r

        # actual visit
        with audits('Viewed multifactor recovery codes', user=True):
            r.form['password'] = 'foo'
            r = r.form.submit()
            assert 'Download' in r
            assert 'Print' in r

        # regenerate codes
        with audits('Regenerated multifactor recovery codes', user=True):
            r = r.forms['multifactor_recovery_regen'].submit()

        # email confirmation
        tasks = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendsimplemail')).all()
        assert len(tasks) == 1
        assert tasks[0].kwargs['subject'] == 'Two-Factor Recovery Codes Regenerated'
        assert 'regenerated' in tasks[0].kwargs['text']

    def test_send_links(self):
        r = self.app.get('/auth/preferences/totp_new')
        r.form['password'] = 'foo'
        r = r.form.submit()

        r = r.forms['totp_send_link'].submit()

        tasks = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendsimplemail')).all()
        assert len(tasks) == 1
        assert tasks[0].kwargs['subject'] == 'Two-Factor Authentication Apps'
        assert 'itunes.apple.com' in tasks[0].kwargs['text']
        assert 'play.google.com' in tasks[0].kwargs['text']
