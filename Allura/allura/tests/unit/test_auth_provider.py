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

import datetime as dt
import calendar

import tg
from mock import Mock
from nose.tools import assert_true, assert_false
from webob import Request

from alluratest.controller import setup_basic_test
from allura.lib import plugin
from allura.lib import helpers as h


class TestAuthenticationProvider(object):

    def setUp(self):
        setup_basic_test()
        self.provider = plugin.AuthenticationProvider(Request.blank('/'))
        self.pwd_updated = dt.datetime.utcnow() - dt.timedelta(days=100)
        self.provider.get_last_password_updated = lambda u: self.pwd_updated
        self.user = Mock()

    def test_is_password_expired_disabled(self):
        assert_false(self.provider.is_password_expired(self.user))

    def test_is_password_expired_days(self):
        with h.push_config(tg.config, **{'auth.pwdexpire.days': '180'}):
            assert_false(self.provider.is_password_expired(self.user))
        with h.push_config(tg.config, **{'auth.pwdexpire.days': '90'}):
            assert_true(self.provider.is_password_expired(self.user))

    def test_is_password_expired_before(self):
        before = dt.datetime.utcnow() - dt.timedelta(days=180)
        before = calendar.timegm(before.timetuple())
        with h.push_config(tg.config, **{'auth.pwdexpire.before': str(before)}):
            assert_false(self.provider.is_password_expired(self.user))

        before = dt.datetime.utcnow() - dt.timedelta(days=1)
        before = calendar.timegm(before.timetuple())
        with h.push_config(tg.config, **{'auth.pwdexpire.before': str(before)}):
            assert_true(self.provider.is_password_expired(self.user))
