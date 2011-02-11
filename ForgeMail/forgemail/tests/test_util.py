# -*- coding: utf-8 -*-
import unittest

from nose.tools import raises, assert_equal
import tg
from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects

from forgemail.lib.util import parse_address
from forgemail.lib.exc import AddressException


COMMON_SUFFIX = tg.config.get('forgemail.domain', '.sourceforge.net')

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
        parse_address('foo@wiki.unicorns.p' + COMMON_SUFFIX)

    @raises(AddressException)
    def test_parse_address_missing_tool(self):
        parse_address('foo@test.p' + COMMON_SUFFIX)

    @raises(AddressException)
    def test_parse_address_bad_tool(self):
        parse_address('foo@hammer.test.p' + COMMON_SUFFIX)

    def test_parse_address_good(self):
        topic, project, app = parse_address('foo@wiki.test.p' + COMMON_SUFFIX)
        assert_equal(topic, 'Wiki.msg.foo')
        assert_equal(project.name, 'test')
        assert_equal(app.__class__.__name__, 'ForgeWikiApp')

