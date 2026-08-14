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

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import mock
import pytest
from ming.odm import ThreadLocalODMSession
from tg import config as tg_config
from smtplib import SMTP as SMTPClient
from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M
from allura.lib.utils import ConfigProxy
from allura.app import Application
from allura.lib.mail_util import (
    parse_address,
    parse_message,
    Header,
    is_autoreply,
    identify_sender,
    _parse_message_id,
    email_policy,
)
from allura.lib.exceptions import AddressException
from allura.tests import decorators as td
from paste.deploy.converters import asint
from allura.command.smtp_server import MailServer
from aiosmtpd.controller import Controller

config = ConfigProxy(
    common_suffix='forgemail.domain',
    return_path='forgemail.return_path')


class TestReactor:

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()
        ThreadLocalODMSession.flush_all()
        ThreadLocalODMSession.close_all()

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
                        charset,
                        policy=email_policy)
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
                      charset,
                      policy=email_policy)
        p2 = MIMEText('''<p>По оживлённым берегам
Громады стройные теснятся
Дворцов и башен; корабли
Толпой со всех концов земли
К богатым пристаням стремятся;</p>'''.encode(charset),
                      'plain',
                      charset,
                      policy=email_policy)
        msg1 = MIMEMultipart(policy=email_policy)
        msg1['Message-ID'] = '<foo@bar.com>'
        msg1.attach(p1)
        msg1.attach(p2)
        s_msg = msg1.as_string()
        msg2 = parse_message(s_msg)
        for part in msg2['parts']:
            if part['payload'] is None:
                continue
            assert isinstance(part['payload'], str), type(part['payload'])

    @mock.patch.dict(tg_config, {
        'forgemail.sender_authentication.header': 'X-Test-Sender-Auth',
    })
    def test_parse_message_preserves_repeated_sender_authentication_headers(self):
        msg = parse_message('''\
From: first@example.com
From: second@example.com
X-Test-Sender-Auth: v=1; dmarc=pass; from-domain=example.com
x-test-sender-auth:
 v=1; result=pass; method=spf-aligned; from-domain=example.com

body''')

        assert msg['from_headers'] == ['first@example.com', 'second@example.com']
        assert msg['sender_authentication_headers'] == [
            'v=1; dmarc=pass; from-domain=example.com',
            '\n v=1; result=pass; method=spf-aligned; from-domain=example.com',
        ]


class TestHeader:

    def test_bytestring(self):
        with pytest.raises(TypeError):
            our_header = Header(b'[asdf2:wiki] Discussion for Home page')
            assert our_header == '[asdf2:wiki] Discussion for Home page'

    def test_ascii(self):
        our_header = Header('[asdf2:wiki] Discussion for Home page')
        assert our_header == '[asdf2:wiki] Discussion for Home page'

    def test_utf8(self):
        our_header = Header('теснятся')
        assert our_header == 'теснятся'

    def test_name_addr(self):
        our_header = Header('"теснятся"', '<dave@b.com>')
        assert our_header == '"теснятся" <dave@b.com>'


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
            mock.Mock(claimed_by_user_id=True, claimed_by_user=lambda: 'user')]
        assert identify_sender(None, 'arg', None, None) == 'user'
        EA.get.assert_called_once_with(email='arg', confirmed=True)

    @mock.patch('allura.model.EmailAddress')
    def test_header(self, EA):
        EA.canonical = lambda e: e
        EA.get.side_effect = [
            None, mock.Mock(claimed_by_user_id=True, claimed_by_user=lambda: 'user')]
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
            None, mock.Mock(claimed_by_user_id=True, claimed_by_user=lambda: 'user')]
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


class TestAuthenticatedIdentifySender:

    HEADER_NAME = 'X-SourceForge-Sender-Auth'
    AUTH_CONFIG = {
        'forgemail.sender_authentication.enabled': 'true',
        'forgemail.sender_authentication.header': HEADER_NAME,
    }
    DMARC_PASS = 'v=1; dmarc=pass; from-domain=users.localhost'
    SPF_ALIGNED_PASS = (
        'v=1; result=pass; method=spf-aligned; '
        'from-domain=users.localhost')

    def setup_method(self, method):
        setup_basic_test()
        setup_global_objects()
        ThreadLocalODMSession.flush_all()

    def _message(self, from_headers=None, sender_authentication_headers=None,
                 header_name=None, extra_headers=None):
        if from_headers is None:
            from_headers = ['"Test Admin" <test-admin@users.localhost>']
        if sender_authentication_headers is None:
            sender_authentication_headers = [self.DMARC_PASS]
        if header_name is None:
            header_name = self.HEADER_NAME
        lines = []
        lines.extend(f'From: {value}' for value in from_headers)
        lines.extend(
            f'{header_name}: {value}'
            for value in sender_authentication_headers)
        lines.extend(extra_headers or [])
        lines.extend(['Subject: inbound sender authentication test', '', 'body'])
        return parse_message('\n'.join(lines))

    def _identify(self, *, peer=('127.0.0.1', 2525),
                  mailfrom='test-admin@users.localhost', from_headers=None,
                  sender_authentication_headers=None, auth_config=None,
                  header_name=None, extra_headers=None):
        if auth_config is None:
            auth_config = self.AUTH_CONFIG
        with mock.patch.dict(tg_config, auth_config):
            msg = self._message(
                from_headers, sender_authentication_headers, header_name,
                extra_headers)
            return identify_sender(peer, mailfrom, msg['headers'], msg)

    def test_disabled_preserves_envelope_sender_lookup(self):
        user = self._identify(
            peer=('203.0.113.10', 2525),
            sender_authentication_headers=[],
            auth_config={
                'forgemail.sender_authentication.enabled': 'false',
                'forgemail.sender_authentication.header': self.HEADER_NAME,
            })

        assert user.username == 'test-admin'

    @pytest.mark.parametrize('sender_authentication_header', [
        DMARC_PASS,
        SPF_ALIGNED_PASS,
        'v=1; dmarc=pass; from-domain=USERS.LOCALHOST',
    ])
    def test_enabled_accepts_unique_confirmed_from_owner(
            self, sender_authentication_header):
        user = self._identify(
            mailfrom='attacker@example.net',
            sender_authentication_headers=[sender_authentication_header])

        assert user.username == 'test-admin'

    def test_enabled_accepts_case_insensitive_canonical_header_name(self):
        header_name = 'x-sourceforge-sender-auth'
        user = self._identify(
            mailfrom='attacker@example.net',
            auth_config={
                'forgemail.sender_authentication.enabled': 'true',
                'forgemail.sender_authentication.header': header_name,
            },
            header_name=header_name)

        assert user.username == 'test-admin'

    def test_enabled_rejects_noncanonical_header_name(self):
        user = self._identify(
            auth_config={
                'forgemail.sender_authentication.enabled': 'true',
                'forgemail.sender_authentication.header': 'X-Other-Sender-Auth',
            })

        assert user.is_anonymous()

    def test_enabled_accepts_folded_header(self):
        user = self._identify(sender_authentication_headers=[
            'v=1; result=pass;\n method=spf-aligned;\n '
            'from-domain=users.localhost',
        ])

        assert user.username == 'test-admin'

    def test_enabled_accepts_encoded_from_display_name(self):
        user = self._identify(
            mailfrom='attacker@example.net',
            from_headers=[
                '=?utf-8?q?J=C3=B6hn?= <test-admin@users.localhost>'])

        assert user.username == 'test-admin'

    @pytest.mark.parametrize('sender_authentication_headers', [
        pytest.param([], id='missing-header'),
        pytest.param([DMARC_PASS, DMARC_PASS], id='duplicate-header'),
        pytest.param(
            ['v=1; dmarc=fail; from-domain=users.localhost'],
            id='dmarc-fail'),
        pytest.param(
            ['v=1; dmarc=none; from-domain=users.localhost'],
            id='dmarc-none-is-not-a-pass'),
        pytest.param(
            ['v=1; result=fail; method=spf-aligned; '
             'from-domain=users.localhost'],
            id='spf-fallback-fail'),
        pytest.param(
            ['v=1; result=pass; method=spf; '
             'from-domain=users.localhost'],
            id='unsupported-method'),
        pytest.param(
            ['v=2; dmarc=pass; from-domain=users.localhost'],
            id='unsupported-version'),
        pytest.param(
            ['dmarc=pass; v=1; from-domain=users.localhost'],
            id='reordered-fields'),
        pytest.param(
            ['v=1; dmarc=pass; from-domain=users.localhost; extra=value'],
            id='extra-field'),
        pytest.param(
            ['note=dmarc=pass; v=1; from-domain=users.localhost'],
            id='dmarc-pass-substring'),
        pytest.param(
            ['v=1; dmarc=pass; from-domain=example.net'],
            id='from-domain-mismatch'),
        pytest.param(
            ['v=1; dmarc=pass; from-domain=users.localhost\x00'],
            id='header-control-character'),
        pytest.param(
            ['v=1; dmarc=pass; from-domain=' + ('a' * 1024)],
            id='header-too-long'),
        pytest.param(
            ['mx.sourceforge.net; dmarc=pass '
             'header.from=users.localhost'],
            id='authentication-results-shape'),
    ])
    def test_enabled_rejects_invalid_authentication_header(
            self, sender_authentication_headers):
        user = self._identify(
            sender_authentication_headers=sender_authentication_headers)

        assert user.is_anonymous()

    def test_enabled_ignores_standard_authentication_results(self):
        user = self._identify(
            sender_authentication_headers=[],
            extra_headers=[
                'Authentication-Results: mx.sourceforge.net; '
                'dmarc=pass header.from=users.localhost',
            ])

        assert user.is_anonymous()

    @pytest.mark.parametrize('from_headers', [
        [],
        ['test-admin@users.localhost', 'other@users.localhost'],
        ['test-admin@users.localhost, other@users.localhost'],
        ['Friends: test-admin@users.localhost;'],
        ['not-an-email-address'],
    ])
    def test_enabled_rejects_ambiguous_from(self, from_headers):
        user = self._identify(from_headers=from_headers)

        assert user.is_anonymous()

    @pytest.mark.parametrize('owner_state', [
        'missing',
        'unconfirmed',
        'disabled',
        'pending',
        'duplicate',
    ])
    def test_enabled_requires_confirmed_unique_active_owner(self, owner_state):
        address = 'authenticated-owner@example.net'
        if owner_state != 'missing':
            owner = M.User.by_username('test-user-1')
            email_address = owner.claim_address(address)
            email_address.confirmed = owner_state != 'unconfirmed'
            if owner_state == 'disabled':
                owner.disabled = True
            elif owner_state == 'pending':
                owner.pending = True
            elif owner_state == 'duplicate':
                other_owner = M.User.by_username('test-user-2')
                other_address = other_owner.claim_address(address)
                other_address.confirmed = True
        ThreadLocalODMSession.flush_all()

        user = self._identify(
            from_headers=[address],
            sender_authentication_headers=[
                'v=1; dmarc=pass; from-domain=example.net'])

        assert user.is_anonymous()

    @pytest.mark.parametrize('auth_config', [
        {
            'forgemail.sender_authentication.enabled': 'unexpected',
            'forgemail.sender_authentication.header': HEADER_NAME,
        },
        {
            'forgemail.sender_authentication.enabled': 'true',
            'forgemail.sender_authentication.header': '',
        },
        {
            'forgemail.sender_authentication.enabled': 'true',
            'forgemail.sender_authentication.header': None,
        },
        {
            'forgemail.sender_authentication.enabled': 'true',
            'forgemail.sender_authentication.header': 'Not A Header Name',
        },
    ])
    def test_invalid_enabled_config_fails_closed(self, auth_config):
        user = self._identify(auth_config=auth_config)

        assert user.is_anonymous()

    @mock.patch(
        'allura.lib.mail_util._authenticated_sender',
        side_effect=RuntimeError('verification failed unexpectedly'))
    def test_enabled_fails_closed_on_unexpected_error(self, authenticated_sender):
        user = self._identify()

        assert user.is_anonymous()
        authenticated_sender.assert_called_once()

    @mock.patch('allura.lib.mail_util.log')
    def test_enabled_logs_authentication_method(self, log):
        user = self._identify(
            sender_authentication_headers=[self.SPF_ALIGNED_PASS])

        assert user.username == 'test-admin'
        log.info.assert_called_once_with(
            'Inbound sender authentication enabled=true result=%s reason=%s '
            'peer=%s',
            True,
            'spf_aligned_pass',
            '127.0.0.1',
        )


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
        hostname = tg_config.get('forgemail.host', '0.0.0.0')
        port = asint(tg_config.get('forgemail.port', 8827))
        handler = MailServer()
        controller = Controller(handler, hostname=hostname, port=port)
        controller.start()

        with SMTPClient(hostname, port, timeout=0.5) as client:
            code, msg = client.ehlo("example.com")
            assert code == 250
            mailfrom = client.docmd("MAIL FROM: <from@example.com>")
            assert mailfrom == (250, b'OK')
            rcpt = client.docmd("RCPT TO: <to@example.com>")
            assert rcpt == (250, b'OK')
            data = client.docmd("DATA")
            assert data == (354, b'End data with <CR><LF>.<CR><LF>')

        with SMTPClient(hostname, port, timeout=0.5) as client:
            client.sendmail('from@example.com', ['to@example.com'], """
            From: From Person <from@example.com>
            To: To Person <to@example.com>
            Subject: A test
            Hi Bart, this is Anne.
            """)

        controller.stop()
