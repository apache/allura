# -*- coding: utf-8 -*-

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

import unittest
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText

import mock
from nose.tools import raises, assert_equal, assert_false, assert_true
from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib.utils import ConfigProxy
from allura.app import Application
from allura.lib.mail_util import (
    parse_address,
    parse_message,
    Header,
    is_autoreply,
    identify_sender,
    _parse_message_id,
)
from allura.lib.exceptions import AddressException
from allura.tests import decorators as td

config = ConfigProxy(
    common_suffix='forgemail.domain',
    return_path='forgemail.return_path')


class TestReactor(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    @raises(AddressException)
    def test_parse_address_bad_domain(self):
        parse_address('foo@bar.com')

    @raises(AddressException)
    def test_parse_address_bad_project(self):
        parse_address('foo@wiki.unicorns.p' + config.common_suffix)

    @raises(AddressException)
    def test_parse_address_missing_tool(self):
        parse_address('foo@test.p' + config.common_suffix)

    @raises(AddressException)
    def test_parse_address_bad_tool(self):
        parse_address('foo@hammer.test.p' + config.common_suffix)

    @td.with_wiki
    def test_parse_address_good(self):
        topic, project, app = parse_address(
            'foo@wiki.test.p' + config.common_suffix)
        assert_equal(topic, 'foo')
        assert_equal(project.shortname, 'test')
        assert_true(isinstance(app, Application))

    def test_unicode_simple_message(self):
        charset = 'utf-8'
        msg1 = MIMEText(u'''По оживлённым берегам
Громады стройные теснятся
Дворцов и башен; корабли
Толпой со всех концов земли
К богатым пристаням стремятся;'''.encode(charset),
                        'plain',
                        charset)
        msg1['Message-ID'] = '<foo@bar.com>'
        s_msg = msg1.as_string()
        msg2 = parse_message(s_msg)
        assert isinstance(msg2['payload'], unicode)

    def test_unicode_complex_message(self):
        charset = 'utf-8'
        p1 = MIMEText(u'''По оживлённым берегам
Громады стройные теснятся
Дворцов и башен; корабли
Толпой со всех концов земли
К богатым пристаням стремятся;'''.encode(charset),
                      'plain',
                      charset)
        p2 = MIMEText(u'''<p>По оживлённым берегам
Громады стройные теснятся
Дворцов и башен; корабли
Толпой со всех концов земли
К богатым пристаням стремятся;</p>'''.encode(charset),
                      'plain',
                      charset)
        msg1 = MIMEMultipart()
        msg1['Message-ID'] = '<foo@bar.com>'
        msg1.attach(p1)
        msg1.attach(p2)
        s_msg = msg1.as_string()
        msg2 = parse_message(s_msg)
        for part in msg2['parts']:
            if part['payload'] is None:
                continue
            assert isinstance(part['payload'], unicode)


class TestHeader(object):

    @raises(TypeError)
    def test_bytestring(self):
        our_header = Header('[asdf2:wiki] Discussion for Home page')
        assert_equal(str(our_header), '[asdf2:wiki] Discussion for Home page')

    def test_ascii(self):
        our_header = Header(u'[asdf2:wiki] Discussion for Home page')
        assert_equal(str(our_header), '[asdf2:wiki] Discussion for Home page')

    def test_utf8(self):
        our_header = Header(u'теснятся')
        assert_equal(str(our_header), '=?utf-8?b?0YLQtdGB0L3Rj9GC0YHRjw==?=')

    def test_name_addr(self):
        our_header = Header(u'"теснятся"', u'<dave@b.com>')
        assert_equal(str(our_header),
                     '=?utf-8?b?ItGC0LXRgdC90Y/RgtGB0Y8i?= <dave@b.com>')


class TestIsAutoreply(object):

    def setUp(self):
        self.msg = {'headers': {}}

    def test_empty(self):
        assert_false(is_autoreply(self.msg))

    def test_gmail(self):
        self.msg['headers']['Auto-Submitted'] = 'auto-replied'
        self.msg['headers']['Precedence'] = 'bulk'
        self.msg['headers']['X-Autoreply'] = 'yes'
        assert_true(is_autoreply(self.msg))

    def test_qmail(self):
        self.msg['headers']['Delivered-To'] = 'Autoresponder'
        assert_true(is_autoreply(self.msg))

    def test_mailtraq(self):
        self.msg['headers']['X-POST-MessageClass'] = '9; Autoresponder'
        assert_true(is_autoreply(self.msg))

    def test_firstclass(self):
        self.msg['headers']['X-FC-MachineGenerated'] = 'true'
        assert_true(is_autoreply(self.msg))

    def test_domain_technologies_control(self):
        self.msg['headers']['X-AutoReply-From'] = 'something'
        self.msg['headers']['X-Mail-Autoreply'] = 'something'
        assert_true(is_autoreply(self.msg))

    def test_communicate_pro(self):
        self.msg['headers']['X-Autogenerated'] = 'Forward'
        assert_true(is_autoreply(self.msg))

    def test_boxtrapper_cpanel(self):
        self.msg['headers']['Preference'] = 'auto_reply'
        self.msg['headers']['X-Precedence'] = 'auto_reply'
        self.msg['headers']['X-Autorespond'] = 'auto_reply'
        assert_true(is_autoreply(self.msg))

    def test_return_path(self):
        self.msg['headers']['Return-Path'] = '<>'
        assert_true(is_autoreply(self.msg))


class TestIdentifySender(object):

    @mock.patch('allura.model.EmailAddress')
    def test_arg(self, EA):
        EA.canonical = lambda e: e
        EA.get.side_effect = [
            mock.Mock(claimed_by_user_id=True, claimed_by_user=lambda:'user')]
        assert_equal(identify_sender(None, 'arg', None, None), 'user')
        EA.get.assert_called_once_with(email='arg', confirmed=True)

    @mock.patch('allura.model.EmailAddress')
    def test_header(self, EA):
        EA.canonical = lambda e: e
        EA.get.side_effect = [
            None, mock.Mock(claimed_by_user_id=True, claimed_by_user=lambda:'user')]
        assert_equal(
            identify_sender(None, 'arg', {'From': 'from'}, None), 'user')
        assert_equal(EA.get.call_args_list,
                     [mock.call(email='arg', confirmed=True), mock.call(email='from')])

    @mock.patch('allura.model.User')
    @mock.patch('allura.model.EmailAddress')
    def test_no_header(self, EA, User):
        anon = User.anonymous()
        EA.canonical = lambda e: e
        EA.get.side_effect = [
            None, mock.Mock(claimed_by_user_id=True, claimed_by_user=lambda:'user')]
        assert_equal(identify_sender(None, 'arg', {}, None), anon)
        assert_equal(EA.get.call_args_list, [mock.call(email='arg', confirmed=True)])

    @mock.patch('allura.model.User')
    @mock.patch('allura.model.EmailAddress')
    def test_no_match(self, EA, User):
        anon = User.anonymous()
        EA.canonical = lambda e: e
        EA.get.side_effect = [None, None]
        assert_equal(
            identify_sender(None, 'arg', {'From': 'from'}, None), anon)
        assert_equal(EA.get.call_args_list,
                     [mock.call(email='arg', confirmed=True), mock.call(email='from')])


def test_parse_message_id():
    assert_equal(_parse_message_id('<de31888f6be2d87dc377d9e713876bb514548625.patches@libjpeg-turbo.p.domain.net>, </p/libjpeg-turbo/patches/54/de31888f6be2d87dc377d9e713876bb514548625.patches@libjpeg-turbo.p.domain.net>'), [
        'de31888f6be2d87dc377d9e713876bb514548625.patches@libjpeg-turbo.p.domain.net',
        'de31888f6be2d87dc377d9e713876bb514548625.patches@libjpeg-turbo.p.domain.net',
    ])
