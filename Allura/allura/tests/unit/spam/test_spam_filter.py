# -*- coding: utf-8 -*-
import mock
import unittest

from allura.lib.spam import SpamFilter


class MockFilter(SpamFilter):
    def check(*args, **kw):
        raise Exception("test exception")
        return True


class TestSpamFilter(unittest.TestCase):
    def test_check(self):
        # default no-op impl always returns False
        self.assertFalse(SpamFilter({}).check('foo'))

    def test_get_default(self):
        config = {}
        entry_points = None
        checker = SpamFilter.get(config, entry_points)
        self.assertTrue(isinstance(checker, SpamFilter))

    def test_get_method(self):
        config = {'spam.method': 'mock'}
        entry_points = {'mock': MockFilter}
        checker = SpamFilter.get(config, entry_points)
        self.assertTrue(isinstance(checker, MockFilter))

    @mock.patch('allura.lib.spam.log')
    def test_exceptionless_check(self, log):
        config = {'spam.method': 'mock'}
        entry_points = {'mock': MockFilter}
        checker = SpamFilter.get(config, entry_points)
        result = checker.check()
        self.assertFalse(result)
        self.assertTrue(log.exception.called)


