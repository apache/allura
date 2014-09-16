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
from pylons import tmpl_context as c
from webob import Request, exc
from bson import ObjectId
from ming.orm.ormsession import ThreadLocalORMSession
from nose.tools import (
    assert_equals,
    assert_equal,
    assert_raises,
    assert_is_none,
    assert_is,
    assert_true,
    assert_false,
)
from mock import Mock, MagicMock, patch

from allura import model as M
from allura.app import Application
from allura.lib import plugin
from allura.lib import helpers as h
from allura.lib.utils import TruthyCallable
from allura.lib.plugin import ProjectRegistrationProvider
from allura.lib.plugin import ThemeProvider
from allura.lib.exceptions import ProjectConflict, ProjectShortnameInvalid
from allura.tests.decorators import audits
from alluratest.controller import setup_basic_test, setup_global_objects


class TestProjectRegistrationProvider(object):

    def setUp(self):
        self.provider = ProjectRegistrationProvider()

    @patch('allura.lib.security.has_access')
    def test_validate_project_15char_user(self, has_access):
        has_access.return_value = TruthyCallable(lambda: True)
        nbhd = M.Neighborhood()
        self.provider.validate_project(
            neighborhood=nbhd,
            shortname='u/' + ('a' * 15),
            project_name='15 char username',
            user=MagicMock(),
            user_project=True,
            private_project=False,
        )

    def test_suggest_name(self):
        f = self.provider.suggest_name
        assert_equals(f('A More Than Fifteen Character Name', Mock()),
                      'amorethanfifteencharactername')

    @patch('allura.model.Project')
    def test_shortname_validator(self, Project):
        Project.query.get.return_value = None
        nbhd = Mock()
        v = self.provider.shortname_validator.to_python

        v('thisislegit', neighborhood=nbhd)
        assert_raises(ProjectShortnameInvalid, v,
                      'not valid', neighborhood=nbhd)
        assert_raises(ProjectShortnameInvalid, v,
                      'this-is-valid-but-too-long', neighborhood=nbhd)
        assert_raises(ProjectShortnameInvalid, v,
                      'this is invalid and too long', neighborhood=nbhd)
        Project.query.get.return_value = Mock()
        assert_raises(ProjectConflict, v, 'thisislegit', neighborhood=nbhd)


class TestThemeProvider(object):

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.response')
    @patch('pylons.request')
    def test_get_site_notification_no_note(self, request, response, SiteNotification):
        SiteNotification.current.return_value = None
        assert_is_none(ThemeProvider().get_site_notification())
        assert not response.set_cookie.called

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.response')
    @patch('pylons.request')
    def test_get_site_notification_closed(self, request, response, SiteNotification):
        SiteNotification.current.return_value._id = 'deadbeef'
        request.cookies = {'site-notification': 'deadbeef-1-true'}
        assert_is_none(ThemeProvider().get_site_notification())
        assert not response.set_cookie.called

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.response')
    @patch('pylons.request')
    def test_get_site_notification_impressions_over(self, request, response, SiteNotification):
        note = SiteNotification.current.return_value
        note._id = 'deadbeef'
        note.impressions = 2
        request.cookies = {'site-notification': 'deadbeef-3-false'}
        assert_is_none(ThemeProvider().get_site_notification())
        assert not response.set_cookie.called

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.response')
    @patch('pylons.request')
    def test_get_site_notification_impressions_under(self, request, response, SiteNotification):
        note = SiteNotification.current.return_value
        note._id = 'deadbeef'
        note.impressions = 2
        request.cookies = {'site-notification': 'deadbeef-1-false'}
        assert_is(ThemeProvider().get_site_notification(), note)
        response.set_cookie.assert_called_once_with(
            'site-notification', 'deadbeef-2-False', max_age=dt.timedelta(days=365))

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.response')
    @patch('pylons.request')
    def test_get_site_notification_impressions_persistent(self, request, response, SiteNotification):
        note = SiteNotification.current.return_value
        note._id = 'deadbeef'
        note.impressions = 0
        request.cookies = {'site-notification': 'deadbeef-1000-false'}
        assert_is(ThemeProvider().get_site_notification(), note)

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.response')
    @patch('pylons.request')
    def test_get_site_notification_new_notification(self, request, response, SiteNotification):
        note = SiteNotification.current.return_value
        note._id = 'deadbeef'
        note.impressions = 1
        request.cookies = {'site-notification': '0ddba11-1000-true'}
        assert_is(ThemeProvider().get_site_notification(), note)
        response.set_cookie.assert_called_once_with(
            'site-notification', 'deadbeef-1-False', max_age=dt.timedelta(days=365))

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.response')
    @patch('pylons.request')
    def test_get_site_notification_no_cookie(self, request, response, SiteNotification):
        note = SiteNotification.current.return_value
        note._id = 'deadbeef'
        note.impressions = 0
        request.cookies = {}
        assert_is(ThemeProvider().get_site_notification(), note)
        response.set_cookie.assert_called_once_with(
            'site-notification', 'deadbeef-1-False', max_age=dt.timedelta(days=365))

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.response')
    @patch('pylons.request')
    def test_get_site_notification_bad_cookie(self, request, response, SiteNotification):
        note = SiteNotification.current.return_value
        note._id = 'deadbeef'
        note.impressions = 0
        request.cookies = {'site-notification': 'deadbeef-1000-true-bad'}
        assert_is(ThemeProvider().get_site_notification(), note)
        response.set_cookie.assert_called_once_with(
            'site-notification', 'deadbeef-1-False', max_age=dt.timedelta(days=365))

    @patch('allura.app.g')
    @patch('allura.lib.plugin.g')
    def test_app_icon_str(self, plugin_g, app_g):
        class TestApp(Application):
            icons = {
                24: 'images/testapp_24.png',
            }
        plugin_g.entry_points = {'tool': {'testapp': TestApp}}
        assert_equals(ThemeProvider().app_icon_url('testapp', 24),
                      app_g.theme_href.return_value)
        app_g.theme_href.assert_called_with('images/testapp_24.png')

    @patch('allura.lib.plugin.g')
    def test_app_icon_str_invalid(self, g):
        g.entry_points = {'tool': {'testapp': Mock()}}
        assert_equals(ThemeProvider().app_icon_url('invalid', 24),
                      None)

    @patch('allura.app.g')
    def test_app_icon_app(self, g):
        class TestApp(Application):
            icons = {
                24: 'images/testapp_24.png',
            }
        app = TestApp(None, None)
        assert_equals(ThemeProvider().app_icon_url(app, 24),
                      g.theme_href.return_value)
        g.theme_href.assert_called_with('images/testapp_24.png')


class TestLocalAuthenticationProvider(object):

    def setUp(self):
        setup_basic_test()
        ThreadLocalORMSession.close_all()
        setup_global_objects()
        self.provider = plugin.LocalAuthenticationProvider(Request.blank('/'))

    def test_password_encoder(self):
        # Verify salt
        ep = self.provider._encode_password
        assert ep('test_pass') != ep('test_pass')
        assert ep('test_pass', '0000') == ep('test_pass', '0000')

    def test_set_password_with_old_password(self):
        user = Mock()
        user.__ming__ = Mock()
        self.provider.validate_password = lambda u, p: False
        assert_raises(
            exc.HTTPUnauthorized,
            self.provider.set_password, user, 'old', 'new')
        assert_equal(user._encode_password.call_count, 0)

        self.provider.validate_password = lambda u, p: True
        self.provider.set_password(user, 'old', 'new')
        user._encode_password.assert_callued_once_with('new')

    def test_set_password_sets_last_updated(self):
        user = Mock()
        user.__ming__ = Mock()
        user.last_password_updated = None
        now1 = dt.datetime.utcnow()
        self.provider.set_password(user, None, 'new')
        now2 = dt.datetime.utcnow()
        assert_true(user.last_password_updated > now1)
        assert_true(user.last_password_updated < now2)

    def test_get_last_password_updated_not_set(self):
        user = Mock()
        user._id = ObjectId()
        user.last_password_updated = None
        upd = self.provider.get_last_password_updated(user)
        gen_time = dt.datetime.utcfromtimestamp(
            calendar.timegm(user._id.generation_time.utctimetuple()))
        assert_equal(upd, gen_time)

    def test_get_last_password_updated(self):
        user = Mock()
        user.last_password_updated = dt.datetime(2014, 06, 04, 13, 13, 13)
        upd = self.provider.get_last_password_updated(user)
        assert_equal(upd, user.last_password_updated)

    def test_enable_user(self):
        user = Mock(disabled=True, __ming__=Mock(), is_anonymous=lambda: False, _id=ObjectId())
        c.user = Mock(username='test-admin')
        with audits('Account enabled by test-admin', user=True):
            self.provider.enable_user(user)
            ThreadLocalORMSession.flush_all()
        assert_equal(user.disabled, False)

    def test_disable_user(self):
        user = Mock(disabled=False, __ming__=Mock(), is_anonymous=lambda: False, _id=ObjectId())
        c.user = Mock(username='test-admin')
        with audits('Account disabled by test-admin', user=True):
            self.provider.disable_user(user)
            ThreadLocalORMSession.flush_all()
        assert_equal(user.disabled, True)

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
