# -*- coding: utf-8 -*-

import mock
import unittest
import urllib

from allura.lib.spam import SpamFilter


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
        entry_points = {'mock': mock.Mock}
        checker = SpamFilter.get(config, entry_points)
        self.assertTrue(isinstance(checker, mock.Mock))

