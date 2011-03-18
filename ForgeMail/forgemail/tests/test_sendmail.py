# -*- coding: utf-8 -*-
import os
import unittest
from datetime import timedelta


from mock import Mock
from pylons import g, c

import ming
from ming.orm import session, ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M
from allura.lib import helpers as h
from forgemail.lib.util import SMTPClient, encode_email_part
from forgemail.reactors import common_react

class TestSendmail(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        self.mail = SMTPClient()
        self.mail._client = Mock(spec=[
                'sendmail'])
        self.mail._client.sendmail = Mock()

    def test_addr(self):
        self.mail.sendmail(
            ['test@example.com'],
            'test@example.com',
            'test@example.com',
            'Subject',
            'message_id@example.com',
            None,
            encode_email_part('Test message', 'text/plain'))
        assert self.mail._client.sendmail.called

    def test_bad_addr(self):
        self.mail.sendmail(
            ['@example.com'],
            'test@example.com',
            'test@example.com',
            'Subject',
            'message_id@example.com',
            None,
            encode_email_part('Test message', 'text/plain'))
        assert not self.mail._client.sendmail.called

    def test_user(self):
        u = M.User.by_username('test-admin')
        u.set_pref('display_name', u'Rick Copeland')
        u.set_pref('email_address', 'test@example.com')
        self.mail.sendmail(
            ['test@example.com'],
            u.email_address_header(),
            u.email_address_header(),
            'Subject',
            'message_id@example.com',
            None,
            encode_email_part('Test message', 'text/plain'))
        assert self.mail._client.sendmail.called
        args, kwargs =  self.mail._client.sendmail.call_args
        assert args[0] == 'noreply@sourceforge.net'
        assert '"Rick Copeland" <test@example.com>' in args[2]

    def test_user_unicode(self):
        u = M.User.by_username('test-admin')
        u.set_pref('display_name', u'Rick Copéland')
        u.set_pref('email_address', 'test@example.com')
        self.mail.sendmail(
            ['test@example.com'],
            u.email_address_header(),
            u.email_address_header(),
            'Subject',
            'message_id@example.com',
            None,
            encode_email_part('Test message', 'text/plain'))
        assert self.mail._client.sendmail.called
        args, kwargs =  self.mail._client.sendmail.call_args
        assert args[0] == 'noreply@sourceforge.net'
        assert '=?utf-8?q?=22Rick_Cop=C3=A9land=22?= <test@example.com>' in args[2]

class TestReactor(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        common_react.smtp_client._client = Mock(spec=[
                'sendmail'])
        common_react.smtp_client._client.sendmail = self.sendmail = Mock()

    def test_send_mail(self):
        addr = 'test@example.com'
        common_react.send_email(None, {
                'from':addr,
                'reply_to':addr,
                'destinations':[addr],
                'message_id':'test@example.com',
                'subject':'Test message',
                'text':'Test message'})
        assert self.sendmail.called
        args, kwargs =  self.sendmail.call_args
        (from_addr, ids, msg) = args
        assert 'Content-Type: text/plain; charset="iso-8859-1"\n' in msg, msg
        assert 'Subject: =?iso-8859-1?q?Test?= =?iso-8859-1?q?message?=\n' in msg, msg

    def test_send_mail_unicode(self):
        addr = 'test@example.com'
        common_react.send_email(None, {
                'from':addr,
                'reply_to':addr,
                'destinations':[addr],
                'message_id':'test@example.com',
                'subject': u'Test ◎ message',
                'text': u'Test ⌘ message'})
        assert self.sendmail.called
        args, kwargs =  self.sendmail.call_args
        (from_addr, ids, msg) = args
        assert 'Content-Type: text/plain; charset="utf-8"\n' in msg, msg
        assert 'Subject: Test =?utf-8?b?4peO?= message\n' in msg, msg

    def test_user(self):
        u = M.User.by_username('test-admin')
        u.set_pref('display_name', u'Rick Copeland')
        u.set_pref('email_address', 'test@example.com')
        addr = str(u._id)
        common_react.send_email(None, {
                'from':addr,
                'reply_to':addr,
                'destinations':[addr],
                'message_id':'test@example.com',
                'subject':'Test message',
                'text':'Test message'})
        assert self.sendmail.called
        args, kwargs =  self.sendmail.call_args
        assert args[0] == 'noreply@sourceforge.net'
        assert '"Rick Copeland" <test@example.com>' in args[2]

    def test_bad_user(self):
        addr = 'test@example.com'
        common_react.send_email(None, {
                'from':addr,
                'reply_to':addr,
                'destinations':[None],
                'message_id':'test@example.com',
                'subject':'Test message',
                'text':'Test message'})
        assert not self.sendmail.called

    def test_user_unicode(self):
        u = M.User.by_username('test-admin')
        u.set_pref('display_name', u'Rick Copéland')
        u.set_pref('email_address', 'test@example.com')
        addr = str(u._id)
        common_react.send_email(None, {
                'from':addr,
                'reply_to':addr,
                'destinations':[addr],
                'message_id':'test@example.com',
                'subject':'Test message',
                'text':'Test message'})
        assert self.sendmail.called
        args, kwargs =  self.sendmail.call_args
        assert args[0] == 'noreply@sourceforge.net'
        assert '=?utf-8?q?=22Rick_Cop=C3=A9land=22?= <test@example.com>' in args[2]
