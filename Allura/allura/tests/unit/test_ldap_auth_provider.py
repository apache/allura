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

import calendar
from datetime import datetime

import pytest
from bson import ObjectId
from mock import patch, Mock
from webob import Request

from allura.tests.test_plugin import TestLocalAuthenticationProvider
from ming.odm.odmsession import ThreadLocalODMSession
from tg import config

from alluratest.controller import setup_basic_test
from allura.lib import plugin
from allura.lib import helpers as h
from allura import model as M


class TestLdapAuthenticationProvider:

    def setup_method(self, method):
        setup_basic_test()
        self.provider = plugin.LdapAuthenticationProvider(Request.blank('/'))

    @pytest.mark.parametrize('algorithm,rounds,specific_salt,salt_len,expected_config', [
        ('2b', None, 'O'*22, None, '{CRYPT}$2b$12'),
        ('5', None, None, None, '{CRYPT}$5$rounds=535000$'),
        ('6', None, None, None, '{CRYPT}$6$rounds=656000$'),
        ('ldap_pbkdf2_sha256', None, None, None, '{PBKDF2-SHA256}29000$'),
        ('ldap_pbkdf2_sha512', None, None, None, '{PBKDF2-SHA512}25000$'),
        ('ldap_bcrypt', None, 'O'*22, None, '{CRYPT}$2b$12$'),
    ])
    def test_password_encoder(self, algorithm: str, rounds, specific_salt, salt_len, expected_config):
        TestLocalAuthenticationProvider._test_password_encoder(
            'auth.ldap.password.',
            self.provider,
            algorithm, rounds, specific_salt, salt_len, expected_config,
        )

    @patch('allura.lib.plugin.ldap')
    def test_set_password(self, ldap):
        user = Mock(username='test-user')
        user.__ming__ = Mock()
        self.provider._encode_password = Mock(return_value=('new-pass-hash', 'somealgo'))
        ldap.dn.escape_dn_chars = lambda x: x

        dn = 'uid=%s,ou=people,dc=localdomain' % user.username
        self.provider.set_password(user, 'old-pass', 'new-pass')
        ldap.initialize.assert_called_once_with('ldaps://localhost/')
        connection = ldap.initialize.return_value
        connection.simple_bind_s.assert_called_once_with(dn, b'old-pass')
        connection.modify_s.assert_called_once_with(
            dn, [(ldap.MOD_REPLACE, 'userPassword', b'new-pass-hash')])
        assert connection.unbind_s.call_count == 1

    @patch('allura.lib.plugin.ldap')
    def test_login(self, ldap):
        params = {
            'username': 'test-user',
            'password': 'test-password',
        }
        self.provider.request.method = 'POST'
        self.provider.request.body = '&'.join([f'{k}={v}' for k, v in params.items()]).encode('utf-8')
        ldap.dn.escape_dn_chars = lambda x: x
        user = M.User.query.get(username=params['username'])
        user.password_algorithm = self.provider._password_algorithm()  # default is non-ldap algo so would cause rehash

        self.provider._login()

        dn = 'uid=%s,ou=people,dc=localdomain' % params['username']
        ldap.initialize.assert_called_with('ldaps://localhost/')
        connection = ldap.initialize.return_value
        connection.simple_bind_s.assert_called_once_with(dn, b'test-password')
        assert connection.unbind_s.call_count == 1

    @patch('allura.lib.plugin.ldap')
    def test_login_autoregister(self, ldap):
        # covers ldap get_pref too, via the display_name fetch
        params = {
            'username': 'abc32590wr38',
            'password': 'test-password',
        }
        self.provider.request.method = 'POST'
        self.provider.request.body = '&'.join([f'{k}={v}' for k, v in params.items()]).encode('utf-8')
        ldap.dn.escape_dn_chars = lambda x: x
        dn = 'uid=%s,ou=people,dc=localdomain' % params['username']
        conn = ldap.initialize.return_value
        conn.search_s.return_value = [(dn, {'cn': ['åℒƒ'.encode()]})]

        self.provider._login()

        user = M.User.query.get(username=params['username'])
        assert user
        assert user.display_name == 'åℒƒ'

    @patch('allura.lib.plugin.modlist')
    @patch('allura.lib.plugin.ldap')
    def test_register_user(self, ldap, modlist):
        user_doc = {
            'username': 'new-user',
            'display_name': 'New User',
            'password': 'new-password',
        }
        ldap.dn.escape_dn_chars = lambda x: x
        self.provider._encode_password = Mock(return_value=('new-password-hash', 'somealgo'))

        assert M.User.query.get(username=user_doc['username']) is None
        with h.push_config(config, **{'auth.ldap.autoregister': 'false'}):
            self.provider.register_user(user_doc)
        ThreadLocalODMSession.flush_all()
        assert M.User.query.get(username=user_doc['username']) is not None

        dn = 'uid=%s,ou=people,dc=localdomain' % user_doc['username']
        ldap.initialize.assert_called_once_with('ldaps://localhost/')
        connection = ldap.initialize.return_value
        connection.simple_bind_s.assert_called_once_with(
            'cn=admin,dc=localdomain',
            'secret')
        connection.add_s.assert_called_once_with(dn, modlist.addModlist.return_value)
        assert connection.unbind_s.call_count == 1

    @patch('allura.lib.plugin.ldap')
    @patch('allura.lib.plugin.datetime', autospec=True)
    def test_set_password_sets_last_updated(self, dt_mock, ldap):
        user = Mock()
        user.__ming__ = Mock()
        user.last_password_updated = None
        self.provider.set_password(user, None, 'new')
        assert user.last_password_updated == dt_mock.utcnow.return_value

    def test_get_last_password_updated_not_set(self):
        user = Mock()
        user._id = ObjectId()
        user.last_password_updated = None
        user.reg_date = None
        upd = self.provider.get_last_password_updated(user)
        gen_time = datetime.utcfromtimestamp(
            calendar.timegm(user._id.generation_time.utctimetuple()))
        assert upd == gen_time

    def test_get_last_password_updated(self):
        user = Mock()
        user.last_password_updated = datetime(2014, 6, 4, 13, 13, 13)
        upd = self.provider.get_last_password_updated(user)
        assert upd == user.last_password_updated
