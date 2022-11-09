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

import mock
import unittest

from ming.odm import ThreadLocalORMSession

from allura.lib.spam import SpamFilter, ChainedSpamFilter
from allura import model as M
from allura.model.artifact import SpamCheckResult
from alluratest.controller import setup_basic_test
from forgewiki import model as WM


class MockFilter(SpamFilter):

    def __init__(self, config):
        self.config = config

    def check(*args, **kw):
        raise Exception("test exception")


class MockFilter2(SpamFilter):

    def __init__(self, config):
        self.config = config

    def check(*args, **kw):
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
        result = checker.check('this is our text')
        self.assertFalse(result)
        self.assertTrue(log.exception.called)


class TestSpamFilterFunctional:

    def setup_method(self, method):
        setup_basic_test()

    def test_record_result(self):
        config = {}
        artifact = WM.Page.query.get()
        user = M.User.query.get(username='test-user')

        SpamFilter(config).record_result(True, artifact, user)
        ThreadLocalORMSession.flush_all()

        results = SpamCheckResult.query.find().all()
        assert len(results) == 1
        assert results[0].result is True
        assert results[0].user.username == 'test-user'


class TestChainedSpamFilter:

    def test(self):
        config = {'spam.method': 'mock1 mock2', 'spam.settingA': 'bcd'}
        entry_points = {'mock1': MockFilter, 'mock2': MockFilter2}
        checker = SpamFilter.get(config, entry_points)
        assert isinstance(checker, ChainedSpamFilter)
        assert len(checker.filters) == 2, checker.filters
        assert checker.filters[0].config == {'spam.method': 'mock1', 'spam.settingA': 'bcd'}
        assert checker.filters[1].config == {'spam.method': 'mock2', 'spam.settingA': 'bcd'}

        assert checker.check()  # first filter errors out (but ignored by `exceptionless`), and 2nd returns True

        checker.submit_spam('some text')
        checker.submit_ham('some text')
