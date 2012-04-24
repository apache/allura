# -*- coding: utf-8 -*-
import unittest
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email import header

from nose.tools import raises, assert_equal
from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib.utils import ConfigProxy

from allura.lib.mail_util import parse_address, parse_message, Header
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
        topic, project, app = parse_address('foo@wiki.test.p' + config.common_suffix)
        assert_equal(topic, 'foo')
        assert_equal(project.name, 'test')
        assert_equal(app.__class__.__name__, 'ForgeWikiApp')

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
            if part['payload'] is None: continue
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
        assert_equal(str(our_header), '=?utf-8?b?ItGC0LXRgdC90Y/RgtGB0Y8i?= <dave@b.com>')