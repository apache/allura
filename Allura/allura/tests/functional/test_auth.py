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

import calendar
from datetime import datetime, time, timedelta
import json
from urlparse import urlparse, parse_qs
from urllib import urlencode
from bson import ObjectId

import re
from ming.orm.ormsession import ThreadLocalORMSession, session
from tg import config, expose
from mock import patch
import mock
from nose.tools import (
    assert_equal,
    assert_not_equal,
    assert_is_none,
    assert_is_not_none,
    assert_in,
    assert_not_in,
    assert_true,
    assert_false,
)
from pylons import tmpl_context as c
from webob import exc

from allura.tests import TestController
from allura.tests import decorators as td
from alluratest.controller import setup_trove_categories
from allura import model as M
from allura.lib import plugin
from allura.lib import helpers as h


def unentity(s):
    return s.replace('&quot;', '"')


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
        ea = M.EmailAddress.find().first()
        r = self.app.get('/auth/verify_addr', params=dict(a=ea.nonce))
        assert json.loads(self.webflash(r))['status'] == 'ok', self.webflash(r)
        r = self.app.get('/auth/logout')
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo',
            _session_id=self.app.cookies['_session_id']))
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='food',
            _session_id=self.app.cookies['_session_id']))
        assert 'Invalid login' in str(r), r.showbrowser()
        r = self.app.post('/auth/do_login', params=dict(
            username='test-usera', password='foo',
            _session_id=self.app.cookies['_session_id']))
        assert 'Invalid login' in str(r), r.showbrowser()

    def test_logout(self):
        self.app.extra_environ = {'disable_auth_magic': 'True'}
        nav_pattern = ('nav', {'class': 'nav-main'})
        r = self.app.get('/auth/')
        f = r.forms[0]
        f['username'] = 'test-user'
        f['password'] = 'foo'
        r = f.submit().follow()
        logged_in_session = r.session['_id']
        links = r.html.find(*nav_pattern).findAll('a')
        assert_equal(links[-1].string, "Log Out")

        r = self.app.get('/auth/logout').follow()
        logged_out_session = r.session['_id']
        assert logged_in_session is not logged_out_session
        links = r.html.find(*nav_pattern).findAll('a')
        assert_equal(links[-1].string, 'Log In')

    def test_track_login(self):
        user = M.User.by_username('test-user')
        assert_equal(user.last_access['login_date'], None)
        assert_equal(user.last_access['login_ip'], None)
        assert_equal(user.last_access['login_ua'], None)

        self.app.get('/')  # establish session
        self.app.post('/auth/do_login',
                      headers={'User-Agent': 'browser'},
                      extra_environ={'REMOTE_ADDR': 'addr'},
                      params=dict(
                          username='test-user',
                          password='foo',
                          _session_id=self.app.cookies['_session_id'],
                      ))
        user = M.User.by_username('test-user')
        assert_not_equal(user.last_access['login_date'], None)
        assert_equal(user.last_access['login_ip'], 'addr')
        assert_equal(user.last_access['login_ua'], 'browser')

    def test_rememberme(self):
        username = M.User.query.get(username='test-user').username

        r = self.app.get('/')  # establish session

        # Login as test-user with remember me checkbox off
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo',
            _session_id=self.app.cookies['_session_id'],
        ))
        assert_equal(r.session['username'], username)
        assert_equal(r.session['login_expires'], True)

        for header, contents in r.headerlist:
            if header == 'Set-cookie':
                assert_not_in('expires', contents)

        # Login as test-user with remember me checkbox on
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo', rememberme='on',
            _session_id=self.app.cookies['_session_id'],
        ))
        assert_equal(r.session['username'], username)
        assert_not_equal(r.session['login_expires'], True)

        for header, contents in r.headerlist:
            if header == 'Set-cookie':
                assert_in('expires', contents)

    @td.with_user_project('test-admin')
    def test_user_can_not_claim_duplicate_emails(self):
        email_address = 'test_abcd_123@domain.net'
        user = M.User.query.get(username='test-admin')
        addresses_number = len(user.email_addresses)
        self.app.get('/')  # establish session
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
        self.app.get('/')  # establish session
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
        assert kwargs['subject'] == u'%s - Email address claim attempt' % config['site_name']
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
        self.app.get('/')  # establish session
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
            self.app.get('/')  # establish session
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
        self.app.get('/')  # establish session
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
        assert kwargs['subject'] == u'%s - Email address claim attempt' % config['site_name']
        assert "You tried to add %s to your Allura account, " \
               "but it is already claimed by your %s account." % (email_address, user.username) in kwargs['text']

    def test_invalidate_verification_link_if_email_was_confirmed(self):
        self.app.get('/')  # establish session
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
        r = self.app.get('/auth/verify_addr', params=dict(a=email.nonce), extra_environ=dict(username='test-user'))

        assert json.loads(self.webflash(r))['status'] == 'error'
        email = M.EmailAddress.find(dict(email=email_address, claimed_by_user_id=user._id)).first()
        assert not email.confirmed

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
        assert_equal(hash, 'generated_hash_value')
        assert_equal(hash_expiry, '04-08-2020')
        return user

    def test_token_generator(self):
        """ Generates new token invalidation tests.

        The tests cover: changing, claiming, updating, removing email addresses.
        :returns: email_change_invalidates_token
        """
        _params = [{'new_addr.addr': 'test_abcd@domain.net',  # Change primary address
                    'primary_addr': 'test@example.com', },
                   {'new_addr.addr': 'test@example.com',  # Claim new address
                    'new_addr.claim': 'Claim Address',
                    'primary_addr': 'test-admin@users.localhost',
                    'password': 'foo',
                    'preferences.email_format': 'plain'},
                   {'addr-1.ord': '1',  # remove test-admin@users.localhost
                    'addr-1.delete': 'on',
                    'addr-2.ord': '2',
                    'new_addr.addr': '',
                    'primary_addr': 'test-admin@users.localhost',
                    'password': 'foo',
                    'preferences.email_format': 'plain'},
                   {'addr-1.ord': '1',  # Remove email
                    'addr-2.ord': '2',
                    'addr-2.delete': 'on',
                    'new_addr.addr': '',
                    'primary_addr': 'test-admin@users.localhost'}]

        for param in _params:
            yield self.email_change_invalidates_token, param

    def email_change_invalidates_token(self, change_params):
        user = self._create_password_reset_hash()
        session(user).flush(user)

        self.app.get('/')  # establish session
        change_params['_session_id'] = self.app.cookies['_session_id']
        self.app.post('/auth/preferences/update_emails',
                      extra_environ=dict(username='test-admin'),
                      params=change_params)

        u = M.User.by_username('test-admin')
        print(u.get_tool_data('AuthPasswordReset', 'hash'))
        assert_equal(u.get_tool_data('AuthPasswordReset', 'hash'), '')
        assert_equal(u.get_tool_data('AuthPasswordReset', 'hash_expiry'), '')

    @td.with_user_project('test-admin')
    def test_change_password(self):
        self.app.get('/')  # establish session
        # Get and assert user with password reset token.
        user = self._create_password_reset_hash()
        old_pass = user.get_pref('password')

        # Change password
        self.app.post('/auth/preferences/change_password',
                      extra_environ=dict(username='test-admin'),
                      params={
                          'oldpw': 'foo',
                          'pw': 'asdfasdf',
                          'pw2': 'asdfasdf',
                          '_session_id': self.app.cookies['_session_id'],
                      })

        # Confirm password was changed.
        assert_not_equal(old_pass, user.get_pref('password'))

        # Confirm any existing tokens were reset.
        assert_equal(user.get_tool_data('AuthPasswordReset', 'hash'), '')
        assert_equal(user.get_tool_data('AuthPasswordReset', 'hash_expiry'), '')

    @td.with_user_project('test-admin')
    def test_prefs(self):
        r = self.app.get('/auth/preferences/',
                         extra_environ=dict(username='test-admin'))
        # check preconditions of test data
        assert 'test@example.com' not in r
        assert 'test-admin@users.localhost' in r
        assert_equal(M.User.query.get(username='test-admin').get_pref('email_address'),
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
        assert_equal(user.get_pref('email_address'), 'test-admin@users.localhost')

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
        r = self.app.get('/auth/preferences/')
        assert 'test-admin@users.localhost' not in r
        # preferred address has not changed if email is not verified
        user = M.User.query.get(username='test-admin')
        assert_equal(user.get_pref('email_address'), None)

        with td.audits('Display Name changed Test Admin => Admin', user=True):
            r = self.app.post('/auth/preferences/update',
                              params={'preferences.display_name': 'Admin',
                                      '_session_id': self.app.cookies['_session_id'],
                                      },
                              extra_environ=dict(username='test-admin'))

    @td.with_user_project('test-admin')
    def test_email_prefs_change_requires_password(self):
        self.app.get('/')  # establish session
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
        assert_in('You must provide your current password to claim new email', self.webflash(r))
        assert_not_in('test@example.com', r.follow())
        new_email_params['password'] = 'bad pass'

        r = self.app.post('/auth/preferences/update_emails',
                          params=new_email_params,
                          extra_environ=dict(username='test-admin'))
        assert_in('You must provide your current password to claim new email', self.webflash(r))
        assert_not_in('test@example.com', r.follow())
        new_email_params['password'] = 'foo'  # valid password

        r = self.app.post('/auth/preferences/update_emails',
                          params=new_email_params,
                          extra_environ=dict(username='test-admin'))
        assert_not_in('You must provide your current password to claim new email', self.webflash(r))
        assert_in('test@example.com', r.follow())

        # Change primary address
        change_primary_params = {
            'new_addr.addr': '',
            'primary_addr': 'test@example.com',
            '_session_id': self.app.cookies['_session_id'],
        }
        r = self.app.post('/auth/preferences/update_emails',
                          params=change_primary_params,
                          extra_environ=dict(username='test-admin'))
        assert_in('You must provide your current password to change primary address', self.webflash(r))
        assert_equal(M.User.by_username('test-admin').get_pref('email_address'), 'test-admin@users.localhost')
        change_primary_params['password'] = 'bad pass'

        r = self.app.post('/auth/preferences/update_emails',
                          params=change_primary_params,
                          extra_environ=dict(username='test-admin'))
        assert_in('You must provide your current password to change primary address', self.webflash(r))
        assert_equal(M.User.by_username('test-admin').get_pref('email_address'), 'test-admin@users.localhost')
        change_primary_params['password'] = 'foo'  # valid password

        r = self.app.post('/auth/preferences/update_emails',
                          params=change_primary_params,
                          extra_environ=dict(username='test-admin'))
        assert_not_in('You must provide your current password to change primary address', self.webflash(r))
        assert_equal(M.User.by_username('test-admin').get_pref('email_address'), 'test@example.com')

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
        assert_in('You must provide your current password to delete an email', self.webflash(r))
        assert_in('test@example.com', r.follow())
        remove_email_params['password'] = 'bad pass'
        r = self.app.post('/auth/preferences/update_emails',
                          params=remove_email_params,
                          extra_environ=dict(username='test-admin'))
        assert_in('You must provide your current password to delete an email', self.webflash(r))
        assert_in('test@example.com', r.follow())
        remove_email_params['password'] = 'foo'  # vallid password
        r = self.app.post('/auth/preferences/update_emails',
                          params=remove_email_params,
                          extra_environ=dict(username='test-admin'))
        assert_not_in('You must provide your current password to delete an email', self.webflash(r))
        assert_not_in('test@example.com', r.follow())

    @td.with_user_project('test-admin')
    def test_prefs_subscriptions(self):
        r = self.app.get('/auth/subscriptions/',
                         extra_environ=dict(username='test-admin'))
        subscriptions = M.Mailbox.query.find(dict(
            user_id=c.user._id, is_flash=False)).all()
        # make sure page actually lists all the user's subscriptions
        assert len(subscriptions) > 0, 'Test user has no subscriptions, cannot verify that they are shown'
        for m in subscriptions:
            assert m._id in r, "Page doesn't list subscription for Mailbox._id = %s" % m._id

        # make sure page lists all tools which user can subscribe
        user = M.User.query.get(username='test-admin')
        for p in user.my_projects():
            for ac in p.app_configs:
                if not M.Mailbox.subscribed(project_id=p._id, app_config_id=ac._id):
                    if ac.tool_name in ('activity', 'admin', 'search', 'userstats', 'profile'):
                        # these have has_notifications=False
                        assert ac._id not in r, "Page lists tool %s but it should not" % ac.tool_name
                    else:
                        assert ac._id in r, "Page doesn't list tool %s" % ac.tool_name

    def _find_subscriptions_form(self, r):
        form = None
        for f in r.forms.itervalues():
            if f.action == 'update_subscriptions':
                form = f
                break
        assert form is not None, "Can't find subscriptions form"
        return form

    def _find_subscriptions_field(self, form, subscribed=False):
        field_name = None
        for k, v in form.fields.iteritems():
            if subscribed:
                check = c and v[0].value == 'on'
            else:
                check = c and v[0].value != 'on'
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
        self.app.get('/')  # establish session
        self.app.post('/auth/subscriptions/update_subscriptions',
                      params={'email_format': 'html', 'subscriptions': '',
                              '_session_id': self.app.cookies['_session_id']})
        r = self.app.get('/auth/subscriptions/')
        assert '<option selected value="html">HTML</option>' in r
        self.app.post('/auth/subscriptions/update_subscriptions',
                      params={'email_format': 'plain', 'subscriptions': '',
                              '_session_id': self.app.cookies['_session_id']})
        r = self.app.get('/auth/subscriptions/')
        assert '<option selected value="plain">Plain Text</option>' in r
        self.app.post('/auth/subscriptions/update_subscriptions',
                      params={'email_format': 'both', 'subscriptions': '',
                              '_session_id': self.app.cookies['_session_id']})
        r = self.app.get('/auth/subscriptions/')
        assert '<option selected value="both">Combined</option>' in r

    def test_create_account(self):
        r = self.app.get('/auth/create_account')
        assert 'Create an Account' in r
        r = self.app.post('/auth/save_new',
                          params=dict(username='AAA', pw='123',
                                      _session_id=self.app.cookies['_session_id']))
        assert_in('Enter a value 6 characters long or more', r)
        assert_in('Usernames must include only small letters, numbers, '
                  'and dashes. They must also start with a letter and be '
                  'at least 3 characters long.', r)
        r = self.app.post(
            '/auth/save_new',
            params=dict(
                username='aaa',
                pw='12345678',
                pw2='12345678',
                display_name='Test Me',
                _session_id=self.app.cookies['_session_id'],
            ))
        r = r.follow()
        assert 'User "aaa" registered' in unentity(r.body)
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
                        _session_id=self.app.cookies['_session_id']),
            status=302)

    def test_create_account_require_email(self):
        self.app.get('/')  # establish session
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
            assert_equal(M.Project.query.find({'name': 'u/aaa'}).count(), 1)
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
            assert_equal(M.Project.query.find({'name': 'u/bbb'}).count(), 0)

    def test_verify_email(self):
        with h.push_config(config, **{'auth.require_email_addr': 'true'}):
            self.app.get('/')  # establish session
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
            assert_equal(M.Project.query.find({'name': 'u/aaa'}).count(), 1)

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
            self.app.get('/')  # establish session
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
        self.app.get('/')  # establish session
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
        assert_equal(r.status_int, 200, 'Redirect to %s' % r.location)
        user.disabled = True
        sess.save(user)
        sess.flush()
        user = M.User.query.get(username='test-admin')
        assert user.disabled
        r = self.app.get('/p/test/admin/',
                         extra_environ={'username': 'test-admin'})
        assert_equal(r.status_int, 302)
        assert_equal(r.location, 'http://localhost/auth/?return_to=%2Fp%2Ftest%2Fadmin%2F')

    def test_no_open_return_to(self):
        r = self.app.get('/auth/logout').follow()
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo',
            return_to='/foo',
            _session_id=self.app.cookies['_session_id']))
        assert_equal(r.location, 'http://localhost/foo')

        r = self.app.get('/auth/logout')
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo',
            return_to='http://localhost:8080/foo',
            _session_id=self.app.cookies['_session_id']))
        assert_equal(r.location, 'http://localhost:8080/foo')

        r = self.app.get('/auth/logout')
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo',
            return_to='http://example.com/foo',
            _session_id=self.app.cookies['_session_id']))
        assert_equal(r.location, 'http://localhost/')

        r = self.app.get('/auth/logout')
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo',
            return_to='//example.com/foo',
            _session_id=self.app.cookies['_session_id']))
        assert_equal(r.location, 'http://localhost/')


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
        assert 'Please enter a valid date' in str(r)
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
        assert_equal(user.socialnetworks[0].socialnetwork, socialnetwork)
        assert_equal(user.socialnetworks[0].accounturl, accounturl)

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
        assert_in({'socialnetwork': socialnetwork, 'accounturl': accounturl}, user.socialnetworks)
        assert_in({'socialnetwork': socialnetwork2, 'accounturl': accounturl2}, user.socialnetworks)

        # Remove first social network account
        self.app.post('/auth/user_info/contacts/remove_social_network',
                      params=dict(socialnetwork=socialnetwork,
                                  account=accounturl,
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 1
        assert_in({'socialnetwork': socialnetwork2, 'accounturl': accounturl2}, user.socialnetworks)

        # Add empty social network account
        self.app.post('/auth/user_info/contacts/add_social_network',
                      params=dict(accounturl=accounturl, socialnetwork='',
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 1
        assert_in({'socialnetwork': socialnetwork2, 'accounturl': accounturl2}, user.socialnetworks)

        # Add invalid social network account
        self.app.post('/auth/user_info/contacts/add_social_network',
                      params=dict(accounturl=accounturl, socialnetwork='invalid',
                                  _session_id=self.app.cookies['_session_id'],
                                  ))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 1
        assert_in({'socialnetwork': socialnetwork2, 'accounturl': accounturl2}, user.socialnetworks)

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
        timeslot1dict = dict(
            week_day=weekday, start_time=starttime, end_time=endtime)
        assert len(
            user.availability) == 1 and timeslot1dict in user.get_availability_timeslots()

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
        timeslot2dict = dict(week_day=weekday2,
                             start_time=starttime2, end_time=endtime2)
        assert len(user.availability) == 2
        assert_in(timeslot1dict, user.get_availability_timeslots())
        assert_in(timeslot2dict, user.get_availability_timeslots())

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
        timeslot2dict = dict(week_day=weekday2,
                             start_time=starttime2, end_time=endtime2)
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
        assert_in(period1dict, user.get_inactive_periods())
        assert_in(period2dict, user.get_inactive_periods())

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
        self.app.get('/')  # establish session
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
            assert_equal(r.body, 'new page')
            self.app.get('/auth/not_page', status=404)


class TestPasswordReset(TestController):
    test_primary_email = 'testprimaryaddr@mail.com'

    @patch('allura.tasks.mail_tasks.sendmail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_email_unconfirmed(self, gen_message_id, sendmail):
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.find(
            {'claimed_by_user_id': user._id}).first()
        email.confirmed = False
        ThreadLocalORMSession.flush_all()
        self.app.get('/')  # establish session
        self.app.post('/auth/password_recovery_hash', {'email': email.email,
                                                       '_session_id': self.app.cookies['_session_id'],
                                                       })
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        assert hash is None

    @patch('allura.tasks.mail_tasks.sendmail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_user_disabled(self, gen_message_id, sendmail):
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.find(
            {'claimed_by_user_id': user._id}).first()
        user.disabled = True
        ThreadLocalORMSession.flush_all()
        self.app.get('/')  # establish session
        self.app.post('/auth/password_recovery_hash', {'email': email.email,
                                                       '_session_id': self.app.cookies['_session_id'],
                                                       })
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        assert hash is None

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_only_primary_email_reset_allowed(self, gen_message_id, sendmail):
        self.app.get('/')  # establish session
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
            assert_equal(kwargs['toaddr'], self.test_primary_email)

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_non_primary_email_reset_allowed(self, gen_message_id, sendmail):
        self.app.get('/')  # establish session
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
            assert_equal(kwargs['toaddr'], email1.email)

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_password_reset(self, gen_message_id, sendmail):
        self.app.get('/')  # establish session
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.find(
            {'claimed_by_user_id': user._id}).first()
        email.confirmed = True
        ThreadLocalORMSession.flush_all()
        old_pw_hash = user.password
        with td.audits('Password recovery link sent to: '+ email.email, user=True):
            r = self.app.post('/auth/password_recovery_hash', {'email': email.email,
                                                               '_session_id': self.app.cookies['_session_id'],
                                                               })
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        hash_expiry = user.get_tool_data('AuthPasswordReset', 'hash_expiry')
        assert hash is not None
        assert hash_expiry is not None

        r = self.app.get('/auth/forgotten_password/%s' % hash)
        assert_in('Enter a new password for: test-admin', r)
        assert_in('New Password:', r)
        assert_in('New Password (again):', r)
        form = r.forms[0]
        form['pw'] = form['pw2'] = new_password = '154321'
        with td.audits('Password changed \(through recovery process\)', user=True):
            # escape parentheses, so they would not be treated as regex group
            r = form.submit()
        user = M.User.query.get(username='test-admin')
        assert_not_equal(old_pw_hash, user.password)
        provider = plugin.LocalAuthenticationProvider(None)
        assert_true(provider._validate_password(user, new_password))

        text = '''Your username is test-admin

To reset your password on %s, please visit the following URL:

%s/auth/forgotten_password/%s''' % (config['site_name'], config['base_url'], hash)

        sendmail.post.assert_called_once_with(
            toaddr=email.email,
            fromaddr=config['forgemail.return_path'],
            reply_to=config['forgemail.return_path'],
            subject='Allura Password recovery',
            message_id=gen_message_id(),
            text=text)
        user = M.User.query.get(username='test-admin')
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        hash_expiry = user.get_tool_data('AuthPasswordReset', 'hash_expiry')
        assert_equal(hash, '')
        assert_equal(hash_expiry, '')

    @patch('allura.tasks.mail_tasks.sendsimplemail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_hash_expired(self, gen_message_id, sendmail):
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.find(
            {'claimed_by_user_id': user._id}).first()
        email.confirmed = True
        ThreadLocalORMSession.flush_all()
        self.app.get('/')  # establish session
        r = self.app.post('/auth/password_recovery_hash', {'email': email.email,
                                                           '_session_id': self.app.cookies['_session_id'],
                                                           })
        user = M.User.by_username('test-admin')
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        user.set_tool_data('AuthPasswordReset',
                           hash_expiry=datetime(2000, 10, 10))
        r = self.app.get('/auth/forgotten_password/%s' % hash.encode('utf-8'))
        assert_in('Unable to process reset, please try again', r.follow().body)
        r = self.app.post('/auth/set_new_password/%s' %
                          hash.encode('utf-8'), {'pw': '154321', 'pw2': '154321',
                                                 '_session_id': self.app.cookies['_session_id'],
                                                 })
        assert_in('Unable to process reset, please try again', r.follow().body)

    @patch('allura.lib.plugin.AuthenticationProvider')
    def test_provider_disabled(self, AP):
        user = M.User.query.get(username='test-admin')
        ap = AP.get()
        ap.forgotten_password_process = False
        ap.authenticate_request()._id = user._id
        ap.by_username().username = user.username
        self.app.get('/auth/forgotten_password', status=404)
        self.app.post('/auth/set_new_password',
                      {'pw': 'foo', 'pw2': 'foo', '_session_id': self.app.cookies['_session_id']},
                      status=404)
        self.app.post('/auth/password_recovery_hash',
                      {'email': 'foo', '_session_id': self.app.cookies['_session_id']},
                      status=404)


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
        assert_equal(r.forms[0].action, 'deregister')
        r.forms[0].submit()
        r = self.app.get('/auth/oauth/')
        assert 'oautstapp' not in r

    def test_generate_revoke_access_token(self):
        # generate
        self.app.get('/')  # establish session
        r = self.app.post('/auth/oauth/register',
                          params={'application_name': 'oautstapp', 'application_description': 'Oauth rulez',
                                  '_session_id': self.app.cookies['_session_id'],
                                  }).follow()
        assert_equal(r.forms[1].action, 'generate_access_token')
        r.forms[1].submit()
        r = self.app.get('/auth/oauth/')
        assert 'Bearer Token:' in r
        assert_not_equal(
            M.OAuthAccessToken.for_user(M.User.by_username('test-admin')), [])
        # revoke
        assert_equal(r.forms[0].action, 'revoke_access_token')
        r.forms[0].submit()
        r = self.app.get('/auth/oauth/')
        assert_not_equal(r.forms[0].action, 'revoke_access_token')
        assert_equal(
            M.OAuthAccessToken.for_user(M.User.by_username('test-admin')), [])

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_interactive(self, Request, Server):
        M.OAuthConsumerToken.consumer = mock.Mock()
        user = M.User.by_username('test-admin')
        M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        ThreadLocalORMSession.flush_all()
        Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_callback': 'http://my.domain.com/callback',
        }
        r = self.app.post('/rest/oauth/request_token', params={})
        rtok = parse_qs(r.body)['oauth_token'][0]
        r = self.app.post('/rest/oauth/authorize',
                          params={'oauth_token': rtok})
        r = r.forms[0].submit('yes')
        assert r.location.startswith('http://my.domain.com/callback')
        pin = parse_qs(urlparse(r.location).query)['oauth_verifier'][0]
        Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': rtok,
            'oauth_verifier': pin,
        }
        r = self.app.get('/rest/oauth/access_token')
        atok = parse_qs(r.body)
        assert_equal(len(atok['oauth_token']), 1)
        assert_equal(len(atok['oauth_token_secret']), 1)

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_request_token_valid(self, Request, Server):
        M.OAuthConsumerToken.consumer = mock.Mock()
        user = M.User.by_username('test-user')
        consumer_token = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        req = Request.from_request.return_value = {'oauth_consumer_key': 'api_key'}
        r = self.app.post('/rest/oauth/request_token', params={'key': 'value'})
        Request.from_request.assert_called_once_with(
            'POST', 'http://localhost/rest/oauth/request_token',
            headers={'Host': 'localhost:80', 'Content-Type': 'application/x-www-form-urlencoded; charset="utf-8"'},
            parameters={'key': 'value'},
            query_string='')
        Server().verify_request.assert_called_once_with(req, consumer_token.consumer, None)
        request_token = M.OAuthRequestToken.query.get(consumer_token_id=consumer_token._id)
        assert_is_not_none(request_token)
        assert_equal(r.body, request_token.to_string())

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_request_token_no_consumer_token(self, Request, Server):
        Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key'}
        self.app.post('/rest/oauth/request_token',
                      params={'key': 'value'}, status=403)

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_request_token_invalid(self, Request, Server):
        Server().verify_request.side_effect = ValueError
        M.OAuthConsumerToken.consumer = mock.Mock()
        user = M.User.by_username('test-user')
        M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        Request.from_request.return_value = {'oauth_consumer_key': 'api_key'}
        self.app.post('/rest/oauth/request_token', params={'key': 'value'}, status=403)

    def test_authorize_ok(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='oob',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/authorize', params={'oauth_token': 'api_key'})
        assert_in('ctok_desc', r.body)
        assert_in('api_key', r.body)

    def test_authorize_invalid(self):
        self.app.post('/rest/oauth/authorize', params={'oauth_token': 'api_key'}, status=403)

    def test_do_authorize_no(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='oob',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        self.app.post('/rest/oauth/do_authorize',
                      params={'no': '1', 'oauth_token': 'api_key'})
        assert_is_none(M.OAuthRequestToken.query.get(api_key='api_key'))

    def test_do_authorize_oob(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='oob',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/do_authorize', params={'yes': '1', 'oauth_token': 'api_key'})
        assert_is_not_none(r.html.find(text=re.compile('^PIN: ')))

    def test_do_authorize_cb(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/do_authorize', params={'yes': '1', 'oauth_token': 'api_key'})
        assert r.location.startswith('http://my.domain.com/callback?oauth_token=api_key&oauth_verifier=')

    def test_do_authorize_cb_params(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/do_authorize', params={'yes': '1', 'oauth_token': 'api_key'})
        assert r.location.startswith('http://my.domain.com/callback?myparam=foo&oauth_token=api_key&oauth_verifier=')

    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_access_token_no_consumer(self, Request):
        Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': 'api_key',
            'oauth_verifier': 'good',
        }
        self.app.get('/rest/oauth/access_token', status=403)

    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_access_token_no_request(self, Request):
        Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': 'api_key',
            'oauth_verifier': 'good',
        }
        user = M.User.by_username('test-admin')
        M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        ThreadLocalORMSession.flush_all()
        self.app.get('/rest/oauth/access_token', status=403)

    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_access_token_bad_pin(self, Request):
        Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': 'api_key',
            'oauth_verifier': 'bad',
        }
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
            validation_pin='good',
        )
        ThreadLocalORMSession.flush_all()
        self.app.get('/rest/oauth/access_token', status=403)

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_access_token_bad_sig(self, Request, Server):
        Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': 'api_key',
            'oauth_verifier': 'good',
        }
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
            validation_pin='good',
        )
        ThreadLocalORMSession.flush_all()
        Server().verify_request.side_effect = ValueError
        self.app.get('/rest/oauth/access_token', status=403)

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_access_token_ok(self, Request, Server):
        Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': 'api_key',
            'oauth_verifier': 'good',
        }
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
            validation_pin='good',
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/rest/oauth/access_token')
        atok = parse_qs(r.body)
        assert_equal(len(atok['oauth_token']), 1)
        assert_equal(len(atok['oauth_token_secret']), 1)


class TestDisableAccount(TestController):
    def test_not_authenticated(self):
        r = self.app.get(
            '/auth/disable/',
            extra_environ={'username': '*anonymous'})
        assert_equal(r.status_int, 302)
        assert_equal(r.location,
                     'http://localhost/auth/?return_to=%2Fauth%2Fdisable%2F')

    def test_lists_user_projects(self):
        r = self.app.get('/auth/disable/')
        user = M.User.by_username('test-admin')
        for p in user.my_projects_by_role_name('Admin'):
            assert_in(p.name, r)
            assert_in(p.url(), r)

    def test_has_asks_password(self):
        r = self.app.get('/auth/disable/')
        form = r.html.find('form', {'action': 'do_disable'})
        assert form is not None

    def test_bad_password(self):
        self.app.get('/')  # establish session
        r = self.app.post('/auth/disable/do_disable', {'password': 'bad',
                                                       '_session_id': self.app.cookies['_session_id'], })
        assert_in('Invalid password', r)
        user = M.User.by_username('test-admin')
        assert_equal(user.disabled, False)

    def test_disable(self):
        self.app.get('/')  # establish session
        r = self.app.post('/auth/disable/do_disable', {'password': 'foo',
                                                       '_session_id': self.app.cookies['_session_id'], })
        assert_equal(r.status_int, 302)
        assert_equal(r.location, 'http://localhost/')
        flash = json.loads(self.webflash(r))
        assert_equal(flash['status'], 'ok')
        assert_equal(flash['message'], 'Your account was successfully disabled!')
        user = M.User.by_username('test-admin')
        assert_equal(user.disabled, True)


class TestPasswordExpire(TestController):
    def login(self, username='test-user', pwd='foo', query_string=''):
        r = self.app.get('/auth/' + query_string, extra_environ={'username': '*anonymous'})
        f = r.forms[0]
        f['username'] = username
        f['password'] = pwd
        return f.submit(extra_environ={'username': '*anonymous'})

    def assert_redirects(self, where='/'):
        try:
            self.app.get(where, extra_environ={'username': 'test-user'}, status=302)
        except exc.HTTPFound as e:
            assert_equal(e.location, '/auth/pwd_expired?' + urlencode({'return_to': where}))

    def assert_not_redirects(self):
        self.app.get('/', extra_environ={'username': 'test-user'}, status=200)

    def test_disabled(self):
        r = self.login()
        assert_false(r.session.get('pwd-expired'))
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
            assert_false(self.expired(r))
            self.assert_not_redirects()

        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login()
            assert_true(self.expired(r))
            self.assert_redirects()

    def test_before(self):
        self.set_expire_for_user()

        before = datetime.utcnow() - timedelta(days=180)
        before = calendar.timegm(before.timetuple())
        with h.push_config(config, **{'auth.pwdexpire.before': before}):
            r = self.login()
            assert_false(self.expired(r))
            self.assert_not_redirects()

        before = datetime.utcnow() - timedelta(days=90)
        before = calendar.timegm(before.timetuple())
        with h.push_config(config, **{'auth.pwdexpire.before': before}):
            r = self.login()
            assert_true(self.expired(r))
            self.assert_redirects()

    def test_logout(self):
        self.set_expire_for_user()
        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login()
            assert_true(self.expired(r))
            self.assert_redirects()
            r = self.app.get('/auth/logout', extra_environ={'username': 'test-user'})
            assert_false(self.expired(r))
            self.assert_not_redirects()

    def test_change_pwd(self):
        self.set_expire_for_user()
        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login()
            assert_true(self.expired(r))
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
            assert_equal(r.location, 'http://localhost/')
            assert_false(self.expired(r))
            user = M.User.by_username('test-user')
            assert_true(user.last_password_updated > old_update_time)
            assert_not_equal(user.password, old_password)

            # Can log in with new password and change isn't required anymore
            r = self.login(pwd='qwerty')
            assert_equal(r.location, 'http://localhost/')
            assert_not_in('Invalid login', r)
            assert_false(self.expired(r))
            self.assert_not_redirects()

            # and can't log in with old password
            r = self.login(pwd='foo')
            assert_in('Invalid login', r)

    def test_expired_pwd_change_invalidates_token(self):
        self.set_expire_for_user()
        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login()
            assert_true(self.expired(r))
            self.assert_redirects()
            user = M.User.by_username('test-user')
            user.set_tool_data('AuthPasswordReset',
                               hash="generated_hash_value",
                               hash_expiry="04-08-2020")
            hash = user.get_tool_data('AuthPasswordReset', 'hash')
            hash_expiry = user.get_tool_data('AuthPasswordReset', 'hash_expiry')
            assert_equal(hash, 'generated_hash_value')
            assert_equal(hash_expiry, '04-08-2020')
            session(user).flush(user)

            # Change expired password
            r = self.app.get('/auth/pwd_expired', extra_environ={'username': 'test-user'})
            f = r.forms[0]
            f['oldpw'] = 'foo'
            f['pw'] = 'qwerty'
            f['pw2'] = 'qwerty'
            r = f.submit(extra_environ={'username': 'test-user'}, status=302)
            assert_equal(r.location, 'http://localhost/')

            user = M.User.by_username('test-user')
            hash = user.get_tool_data('AuthPasswordReset', 'hash')
            hash_expiry = user.get_tool_data('AuthPasswordReset', 'hash_expiry')

            assert_equal(hash, '')
            assert_equal(hash_expiry, '')

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
        assert_true(self.expired(r))
        user = M.User.by_username('test-user')
        assert_equal(user.last_password_updated, old_update_time)
        assert_equal(user.password, old_password)
        return r

    def test_change_pwd_validation(self):
        self.set_expire_for_user()
        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login()
            assert_true(self.expired(r))
            self.assert_redirects()

            r = self.check_validation('', '', '')
            assert_in('Please enter a value', r)
            r = self.check_validation('', 'qwe', 'qwerty')
            assert_in('Enter a value 6 characters long or more', r)
            r = self.check_validation('bad', 'qwerty1', 'qwerty')
            assert_in('Passwords must match', r)
            r = self.check_validation('bad', 'qwerty', 'qwerty')
            assert_in('Incorrect password', self.webflash(r))
            assert_equal(r.location, 'http://localhost/auth/pwd_expired?return_to=')

            with h.push_config(config, **{'auth.min_password_len': 3}):
                r = self.check_validation('foo', 'foo', 'foo')
                assert_in('Your old and new password should not be the same', r)

    def test_return_to(self):
        return_to = '/p/test/tickets/?milestone=1.0&page=2'
        self.set_expire_for_user()
        with h.push_config(config, **{'auth.pwdexpire.days': 90}):
            r = self.login(query_string='?' + urlencode({'return_to': return_to}))
            # don't go to the return_to yet
            assert_equal(r.location, 'http://localhost/auth/pwd_expired?' + urlencode({'return_to': return_to}))

            # but if user tries to go directly there anyway, intercept and redirect back
            self.assert_redirects(where=return_to)

            r = self.app.get('/auth/pwd_expired', extra_environ={'username': 'test-user'})
            f = r.forms[0]
            f['oldpw'] = 'foo'
            f['pw'] = 'qwerty'
            f['pw2'] = 'qwerty'
            f['return_to'] = return_to
            r = f.submit(extra_environ={'username': 'test-user'}, status=302)
            assert_equal(r.location, 'http://localhost/p/test/tickets/?milestone=1.0&page=2')


class TestCSRFProtection(TestController):
    def test_blocks_invalid(self):
        # so test-admin isn't automatically logged in for all requests
        self.app.extra_environ = {'disable_auth_magic': 'True'}

        # regular login
        r = self.app.get('/auth/')
        r.form['username'] = 'test-admin'
        r.form['password'] = 'foo'
        r.form.submit()

        # regular form submit
        r = self.app.get('/admin/overview')
        r = r.form.submit()
        assert_equal(r.location, 'http://localhost/admin/overview')

        # invalid form submit
        r = self.app.get('/admin/overview')
        r.form['_session_id'] = 'bogus'
        r = r.form.submit()
        assert_equal(r.location, 'http://localhost/auth/')

    def test_blocks_invalid_on_login(self):
        r = self.app.get('/auth/')
        r.form['_session_id'] = 'bogus'
        r.form.submit(status=403)

    def test_token_present_on_first_request(self):
        r = self.app.get('/auth/')
        assert_true(r.form['_session_id'].value)
