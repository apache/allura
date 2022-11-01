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
from six.moves.email_mime_multipart import MIMEMultipart
from six.moves.email_mime_text import MIMEText

import mock
import pytest
from ming.orm import ThreadLocalORMSession
from tg import config as tg_config

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.command.smtp_server import MailServer
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

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_parse_address_bad_domain(self):
        with pytest.raises(AddressException):
            parse_address('foo@bar.com')

    @td.with_wiki
    @mock.patch.dict(tg_config, {'forgemail.domain.alternates': '.secondary.com .tertiary.com'})
    def test_parse_address_alternate_domain(self):
        parse_address('foo@wiki.test.p.secondary.com')
        parse_address('foo@wiki.test.p.tertiary.com')

    def test_parse_address_bad_project(self):
        with pytest.raises(AddressException):
            parse_address('foo@wiki.unicorns.p' + config.common_suffix)

    def test_parse_address_missing_tool(self):
        with pytest.raises(AddressException):
            parse_address('foo@test.p' + config.common_suffix)

    def test_parse_address_bad_tool(self):
        with pytest.raises(AddressException):
            parse_address('foo@hammer.test.p' + config.common_suffix)

    @td.with_wiki
    def test_parse_address_good(self):
        topic, project, app = parse_address(
            'foo@wiki.test.p' + config.common_suffix)
        assert topic == 'foo'
        assert project.shortname == 'test'
        assert isinstance(app, Application)

    def test_unicode_simple_message(self):
        charset = 'utf-8'
        msg1 = MIMEText('''По оживлённым берегам
Громады стройные теснятся
Дворцов и башен; корабли
Толпой со всех концов земли
К богатым пристаням стремятся;'''.encode(charset),
                        'plain',
                        charset)
        msg1['Message-ID'] = '<foo@bar.com>'
        s_msg = msg1.as_string()
        msg2 = parse_message(s_msg)
        assert isinstance(msg2['payload'], str)
        assert 'всех' in msg2['payload']

    def test_more_encodings(self):
        # these are unicode strings to reflect behavior after loading 'route_email' tasks from mongo
        s_msg = """Date: Sat, 25 May 2019 09:32:00 +1000
From: <foo@bar.com>
To: <385@bugs.proj.localhost>
Subject: bugs
Content-Type: text/plain; charset=GBK
Content-Transfer-Encoding: base64

VGhlIFNuYXA3IGFwcGxpY2F0aW9uKGJhc2VkIG9uIHNuYXA3LWZ1bGwtMS40LjIpIGhhcyBiZWVu
IHJ1biBvdmVyIGEgd2VlayBvbiBRTlg2LjYuMCwKQnV0IHNvbWV0aW1lcyAsc3lzdGVtIHNjcmVl
biB3aWxsIHByaW50CiJsZGQ6RkFUQUw6Y291bGQgbm90IGxvYWQgbGlicmFyeSBsaWJzb2NrZXQu
c28uMyIsClRoZSBhcHBsaWNhdGlvbidzIGNvbW11bmljYXRpb24gd29yayB3ZWxsICxidXQgdGhl
IGZ0cCx0ZWxuZXQscGluZyBjYW4ndCB3b3JrICEKCgpXaHk/
"""
        msg = parse_message(s_msg)
        assert isinstance(msg['payload'], str)
        assert 'The Snap7 application' in msg['payload']

        s_msg = """Date: Sat, 25 May 2019 09:32:00 +1000
From: <foo@bar.com>
To: <385@bugs.proj.localhost>
Subject: bugs
Content-Type: text/plain; charset=utf-8
Content-Disposition: inline
Content-Transfer-Encoding: 8bit

> Status: closed
> Created: Thu May 23, 2019 09:24 PM UTC by admin1
> Attachments:
>
>   • foo.txt (1.0 kB; text/plain)
>
"""
        msg = parse_message(s_msg)
        assert isinstance(msg['payload'], str)
        assert '• foo' in msg['payload']

        s_msg = """Date: Sat, 25 May 2019 09:32:00 +1000
From: <foo@bar.com>
To: <385@bugs.proj.localhost>
Subject: bugs
Content-Type: TEXT/PLAIN; format=flowed; charset=ISO-8859-15
Content-Transfer-Encoding: 8BIT

programmed or èrogrammed ?
"""
        msg = parse_message(s_msg)
        assert isinstance(msg['payload'], str)
        assert 'èrogrammed' in msg['payload']

    def test_more_encodings_multipart(self):
        # these are unicode strings to reflect behavior after loading 'route_email' tasks from mongo
        s_msg = """Date: Sat, 25 May 2019 09:32:00 +1000
From: <foo@bar.com>
To: <385@bugs.proj.localhost>
Subject: bugs
Content-Type: multipart/alternative; boundary="===============7387203749754534836=="

--===============7387203749754534836==
Content-Type: text/plain; charset="utf-8"

> Status: closed
> Created: Thu May 23, 2019 09:24 PM UTC by admin1
> Attachments:
>
>   • foo.txt (1.0 kB; text/plain)
>


--===============7387203749754534836==
Content-Type: text/html; charset="utf-8"

<html><head>... blah blah
...
&gt; • foo.txt (1.0 kB; text/plain)
"""
        msg = parse_message(s_msg)
        assert isinstance(msg['parts'][1]['payload'], str)
        assert isinstance(msg['parts'][2]['payload'], str)
        assert '• foo' in msg['parts'][1]['payload']
        assert '• foo' in msg['parts'][2]['payload']

    def test_unicode_complex_message(self):
        charset = 'utf-8'
        p1 = MIMEText('''По оживлённым берегам
Громады стройные теснятся
Дворцов и башен; корабли
Толпой со всех концов земли
К богатым пристаням стремятся;'''.encode(charset),
                      'plain',
                      charset)
        p2 = MIMEText('''<p>По оживлённым берегам
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
            assert isinstance(part['payload'], str), type(part['payload'])


class TestHeader:

    def test_bytestring(self):
        with pytest.raises(TypeError):
            our_header = Header(b'[asdf2:wiki] Discussion for Home page')
            assert our_header.encode() == '[asdf2:wiki] Discussion for Home page'

    def test_ascii(self):
        our_header = Header('[asdf2:wiki] Discussion for Home page')
        assert our_header.encode() == '[asdf2:wiki] Discussion for Home page'

    def test_utf8(self):
        our_header = Header('теснятся')
        assert our_header.encode() == '=?utf-8?b?0YLQtdGB0L3Rj9GC0YHRjw==?='

    def test_name_addr(self):
        our_header = Header('"теснятся"', '<dave@b.com>')
        assert (our_header.encode() ==
                     '=?utf-8?b?ItGC0LXRgdC90Y/RgtGB0Y8i?= <dave@b.com>')


class TestIsAutoreply:

    def setup_method(self, method):
        self.msg = {'headers': {}}

    def test_empty(self):
        assert not is_autoreply(self.msg)

    def test_gmail(self):
        self.msg['headers']['Auto-Submitted'] = 'auto-replied'
        self.msg['headers']['Precedence'] = 'bulk'
        self.msg['headers']['X-Autoreply'] = 'yes'
        assert is_autoreply(self.msg)

    def test_qmail(self):
        self.msg['headers']['Delivered-To'] = 'Autoresponder'
        assert is_autoreply(self.msg)

    def test_mailtraq(self):
        self.msg['headers']['X-POST-MessageClass'] = '9; Autoresponder'
        assert is_autoreply(self.msg)

    def test_firstclass(self):
        self.msg['headers']['X-FC-MachineGenerated'] = 'true'
        assert is_autoreply(self.msg)

    def test_domain_technologies_control(self):
        self.msg['headers']['X-AutoReply-From'] = 'something'
        self.msg['headers']['X-Mail-Autoreply'] = 'something'
        assert is_autoreply(self.msg)

    def test_communicate_pro(self):
        self.msg['headers']['X-Autogenerated'] = 'Forward'
        assert is_autoreply(self.msg)

    def test_boxtrapper_cpanel(self):
        self.msg['headers']['Preference'] = 'auto_reply'
        self.msg['headers']['X-Precedence'] = 'auto_reply'
        self.msg['headers']['X-Autorespond'] = 'auto_reply'
        assert is_autoreply(self.msg)

    def test_return_path(self):
        self.msg['headers']['Return-Path'] = '<>'
        assert is_autoreply(self.msg)


class TestIdentifySender:

    @mock.patch('allura.model.EmailAddress')
    def test_arg(self, EA):
        EA.canonical = lambda e: e
        EA.get.side_effect = [
            mock.Mock(claimed_by_user_id=True, claimed_by_user=lambda:'user')]
        assert identify_sender(None, 'arg', None, None) == 'user'
        EA.get.assert_called_once_with(email='arg', confirmed=True)

    @mock.patch('allura.model.EmailAddress')
    def test_header(self, EA):
        EA.canonical = lambda e: e
        EA.get.side_effect = [
            None, mock.Mock(claimed_by_user_id=True, claimed_by_user=lambda:'user')]
        assert (
            identify_sender(None, 'arg', {'From': 'from'}, None) == 'user')
        assert (EA.get.call_args_list ==
                     [mock.call(email='arg', confirmed=True), mock.call(email='from')])

    @mock.patch('allura.model.User')
    @mock.patch('allura.model.EmailAddress')
    def test_no_header(self, EA, User):
        anon = User.anonymous()
        EA.canonical = lambda e: e
        EA.get.side_effect = [
            None, mock.Mock(claimed_by_user_id=True, claimed_by_user=lambda:'user')]
        assert identify_sender(None, 'arg', {}, None) == anon
        assert EA.get.call_args_list == [mock.call(email='arg', confirmed=True)]

    @mock.patch('allura.model.User')
    @mock.patch('allura.model.EmailAddress')
    def test_no_match(self, EA, User):
        anon = User.anonymous()
        EA.canonical = lambda e: e
        EA.get.side_effect = [None, None]
        assert (
            identify_sender(None, 'arg', {'From': 'from'}, None) == anon)
        assert (EA.get.call_args_list ==
                     [mock.call(email='arg', confirmed=True), mock.call(email='from')])


def test_parse_message_id():
    assert _parse_message_id('<de31888f6be2d87dc377d9e713876bb514548625.patches@libjpeg-turbo.p.domain.net>, </p/libjpeg-turbo/patches/54/de31888f6be2d87dc377d9e713876bb514548625.patches@libjpeg-turbo.p.domain.net>') == [
        'de31888f6be2d87dc377d9e713876bb514548625.patches@libjpeg-turbo.p.domain.net',
        'de31888f6be2d87dc377d9e713876bb514548625.patches@libjpeg-turbo.p.domain.net',
    ]


class TestMailServer:

    def setup_method(self, method):
        setup_basic_test()

    @mock.patch('allura.command.base.log', autospec=True)
    def test(self, log):
        listen_port = ('0.0.0.0', 8825)
        mailserver = MailServer(listen_port, None)
        mailserver.process_message('127.0.0.1', 'foo@bar.com', ['1234@tickets.test.p.localhost'],
                                   'this is the email body with headers and everything ÎÅ¸'.encode())
        assert [] == log.exception.call_args_list
        assert log.info.call_args[0][0].startswith('Msg passed along as task '), log.info.call_args
