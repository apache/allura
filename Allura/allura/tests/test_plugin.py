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
from allura.lib import phone
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
        assert_raises(ProjectShortnameInvalid, v,
                      'end-dash-', neighborhood=nbhd)
        Project.query.get.return_value = Mock()
        assert_raises(ProjectConflict, v, 'thisislegit', neighborhood=nbhd)


class TestProjectRegistrationProviderParseProjectFromUrl(object):

    def setUp(self):
        setup_basic_test()
        ThreadLocalORMSession.close_all()
        setup_global_objects()
        self.provider = ProjectRegistrationProvider()
        self.parse = self.provider.project_from_url

    def test_empty_url(self):
        assert_equal((None, u'Empty url'), self.parse(None))
        assert_equal((None, u'Empty url'), self.parse(''))
        assert_equal((None, u'Empty url'), self.parse('/'))

    def test_neighborhood_not_found(self):
        assert_equal((None, u'Neighborhood not found'), self.parse('/nbhd/project'))

    def test_project_not_found(self):
        assert_equal((None, u'Project not found'), self.parse('/p/project'))
        assert_equal((None, u'Project not found'), self.parse('project'))

    def test_ok_full(self):
        p = M.Project.query.get(shortname='test')
        adobe = M.Project.query.get(shortname='adobe-1')
        assert_equal((p, None), self.parse('p/test'))
        assert_equal((p, None), self.parse('/p/test'))
        assert_equal((p, None), self.parse('/p/test/tickets/1'))
        assert_equal((p, None), self.parse('http://localhost:8080/p/test/tickets/1'))
        assert_equal((adobe, None), self.parse('/adobe/adobe-1/'))

    def test_only_shortname_multiple_projects_matched(self):
        adobe_n = M.Neighborhood.query.get(url_prefix='/adobe/')
        M.Project(shortname='test', neighborhood_id=adobe_n._id)
        ThreadLocalORMSession.flush_all()
        assert_equal((None, u'Too many matches for project: 2'), self.parse('test'))

    def test_only_shortname_ok(self):
        p = M.Project.query.get(shortname='test')
        adobe = M.Project.query.get(shortname='adobe-1')
        assert_equal((p, None), self.parse('test'))
        assert_equal((adobe, None), self.parse('adobe-1'))

    def test_subproject(self):
        p = M.Project.query.get(shortname='test/sub1')
        assert_equal((p, None), self.parse('p/test/sub1'))
        assert_equal((p, None), self.parse('p/test/sub1/something'))
        assert_equal((p, None), self.parse('http://localhost:8080/p/test/sub1'))
        assert_equal((p, None), self.parse('http://localhost:8080/p/test/sub1/something'))

    def test_subproject_not_found(self):
        p = M.Project.query.get(shortname='test')
        assert_equal((p, None), self.parse('http://localhost:8080/p/test/not-a-sub'))


class UserMock(object):
    def __init__(self):
        self.tool_data = {}
        self._projects = []

    def get_tool_data(self, tool, key):
        return self.tool_data.get(tool, {}).get(key, None)

    def set_tool_data(self, tool, **kw):
        d = self.tool_data.setdefault(tool, {})
        d.update(kw)

    def set_projects(self, projects):
        self._projects = projects

    def my_projects_by_role_name(self, role):
        return self._projects


class TestProjectRegistrationProviderPhoneVerification(object):

    def setUp(self):
        self.p = ProjectRegistrationProvider()
        self.user = UserMock()
        self.nbhd = MagicMock()

    def test_phone_verified_disabled(self):
        with h.push_config(tg.config, **{'project.verify_phone': 'false'}):
            assert_true(self.p.phone_verified(self.user, self.nbhd))

    @patch.object(plugin.security, 'has_access', autospec=True)
    def test_phone_verified_admin(self, has_access):
        has_access.return_value.return_value = True
        with h.push_config(tg.config, **{'project.verify_phone': 'true'}):
            assert_true(self.p.phone_verified(self.user, self.nbhd))

    @patch.object(plugin.security, 'has_access', autospec=True)
    def test_phone_verified_project_admin(self, has_access):
        has_access.return_value.return_value = False
        with h.push_config(tg.config, **{'project.verify_phone': 'true'}):
            self.user.set_projects([Mock()])
            assert_false(self.p.phone_verified(self.user, self.nbhd))
            self.user.set_projects([Mock(neighborhood_id=self.nbhd._id)])
            assert_true(self.p.phone_verified(self.user, self.nbhd))

    @patch.object(plugin.security, 'has_access', autospec=True)
    def test_phone_verified(self, has_access):
        has_access.return_value.return_value = False
        with h.push_config(tg.config, **{'project.verify_phone': 'true'}):
            assert_false(self.p.phone_verified(self.user, self.nbhd))
            self.user.set_tool_data('phone_verification', number_hash='123')
            assert_true(self.p.phone_verified(self.user, self.nbhd))

    @patch.object(plugin, 'g')
    def test_verify_phone_disabled(self, g):
        g.phone_service = Mock(spec=phone.PhoneService)
        with h.push_config(tg.config, **{'project.verify_phone': 'false'}):
            result = self.p.verify_phone(self.user, '12345')
            assert_false(g.phone_service.verify.called)
            assert_equal(result, {'status': 'ok'})

    @patch.object(plugin, 'g')
    def test_verify_phone(self, g):
        g.phone_service = Mock(spec=phone.PhoneService)
        with h.push_config(tg.config, **{'project.verify_phone': 'true'}):
            result = self.p.verify_phone(self.user, '123 45 45')
            g.phone_service.verify.assert_called_once_with('1234545')
            assert_equal(result, g.phone_service.verify.return_value)

    @patch.object(plugin, 'g')
    def test_check_phone_verification_disabled(self, g):
        g.phone_service = Mock(spec=phone.PhoneService)
        with h.push_config(tg.config, **{'project.verify_phone': 'false'}):
            result = self.p.check_phone_verification(
                self.user, 'request-id', '1111', 'hash')
            assert_false(g.phone_service.check.called)
            assert_equal(result, {'status': 'ok'})

    @patch.object(plugin.h, 'auditlog_user', autospec=True)
    @patch.object(plugin, 'g')
    def test_check_phone_verification_fail(self, g, audit):
        g.phone_service = Mock(spec=phone.PhoneService)
        with h.push_config(tg.config, **{'project.verify_phone': 'true'}):
            result = self.p.check_phone_verification(
                self.user, 'request-id', '1111', 'hash')
            g.phone_service.check.assert_called_once_with(
                'request-id', '1111')
            assert_equal(result, g.phone_service.check.return_value)
            assert_equal(
                self.user.get_tool_data('phone_verification', 'number_hash'),
                None)
            audit.assert_called_once_with(
                'Phone verification failed. Hash: hash', user=self.user)

    @patch.object(plugin.h, 'auditlog_user', autospec=True)
    @patch.object(plugin, 'g')
    def test_check_phone_verification_success(self, g, audit):
        g.phone_service = Mock(spec=phone.PhoneService)
        with h.push_config(tg.config, **{'project.verify_phone': 'true'}):
            g.phone_service.check.return_value = {'status': 'ok'}
            result = self.p.check_phone_verification(
                self.user, 'request-id', '1111', 'hash')
            g.phone_service.check.assert_called_once_with(
                'request-id', '1111')
            assert_equal(
                self.user.get_tool_data('phone_verification', 'number_hash'),
                'hash')
            audit.assert_called_once_with(
                'Phone verification succeeded. Hash: hash', user=self.user)


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
        SiteNotification.current.return_value.user_role = None
        SiteNotification.current.return_value.page_regex = None
        SiteNotification.current.return_value.page_tool_type = None
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
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
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
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
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
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        request.cookies = {'site-notification': 'deadbeef-1000-false'}
        assert_is(ThemeProvider().get_site_notification(), note)

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.response')
    @patch('pylons.request')
    def test_get_site_notification_new_notification(self, request, response, SiteNotification):
        note = SiteNotification.current.return_value
        note._id = 'deadbeef'
        note.impressions = 1
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
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
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
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
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
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

    @patch('pylons.tmpl_context.user')
    @patch('allura.model.notification.SiteNotification')
    def test_get_site_notification_with_role(self, SiteNotification, User):
        note = SiteNotification.current.return_value
        note.user_role = 'Test'
        note.page_regex = None
        note.page_tool_type = None
        projects = User.my_projects_by_role_name

        User.is_anonymous.return_value = True
        assert_is(ThemeProvider().get_site_notification(), None)

        User.is_anonymous.return_value = False
        projects.return_value = []
        assert_is(ThemeProvider().get_site_notification(), None)

        projects.return_value = [Mock()]
        projects.return_value[0].is_user_project = True
        assert_is(ThemeProvider().get_site_notification(), None)

        projects.return_value[0].is_user_project = False
        assert_is(ThemeProvider().get_site_notification(), note)

        projects.projects.return_value = [Mock(), Mock()]
        assert_is(ThemeProvider().get_site_notification(), note)

    @patch('allura.model.notification.SiteNotification')
    def test_get_site_notification_without_role(self, SiteNotification):
        note = SiteNotification.current.return_value
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        assert_is(ThemeProvider().get_site_notification(), note)

    @patch('re.search')
    @patch('allura.model.notification.SiteNotification')
    def test_get_site_notification_with_page_regex(self, SiteNotification, search):
        note = SiteNotification.current.return_value
        note.user_role = None
        note.page_regex = 'test'
        note.page_tool_type = None

        search.return_value = True
        assert_is(ThemeProvider().get_site_notification(), note)

        search.return_value = None
        assert_is(ThemeProvider().get_site_notification(), None)

    @patch('allura.model.notification.SiteNotification')
    def test_get_site_notification_with_page_tool_type(self, SiteNotification):
        note = SiteNotification.current.return_value
        note.user_role = None
        note.page_regex = None
        c.app = Mock()
        note.page_tool_type.lower.return_value = 'test1'

        c.app.config.tool_name.lower.return_value = 'test1'
        assert_is(ThemeProvider().get_site_notification(), note)

        c.app.config.tool_name.lower.return_value = 'test2'
        assert_is(ThemeProvider().get_site_notification(), None)

        c.app = None
        assert_is(ThemeProvider().get_site_notification(), None)

    @patch('pylons.request')
    @patch('allura.model.notification.SiteNotification')
    def test_get_site_notification_with_page_tool_type_page_regex(self, SiteNotification, request):
        note = SiteNotification.current.return_value
        note.user_role = None
        note.page_regex = 'test'
        c.app = Mock()
        note.page_tool_type.lower.return_value = 'test1'

        request.path_qs = 'ttt'
        c.app.config.tool_name.lower.return_value = 'test2'
        assert_is(ThemeProvider().get_site_notification(), None)

        request.path_qs = 'test'
        assert_is(ThemeProvider().get_site_notification(), None)

        request.path_qs = 'ttt'
        c.app.config.tool_name.lower.return_value = 'test1'
        assert_is(ThemeProvider().get_site_notification(), None)

        request.path_qs = 'test'
        assert_is(ThemeProvider().get_site_notification(), note)

        c.app = None
        assert_is(ThemeProvider().get_site_notification(), None)

        request.path_qs = 'ttt'
        assert_is(ThemeProvider().get_site_notification(), None)

    @patch('allura.model.notification.SiteNotification')
    def test_get__site_notification(self, SiteNotification):
        note = SiteNotification.current.return_value
        note._id = 'test_id'
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        get_note = ThemeProvider()._get_site_notification()

        assert isinstance(get_note, tuple)
        assert len(get_note) is 2
        assert get_note[0] is note
        assert get_note[1] == 'test_id-1-False'

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.request')
    def test_get_site_notifications_with_api_cookie(self, request, SiteNotification):
        note = SiteNotification.current.return_value
        note._id = 'test_id'
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        request.cookies = {}
        get_note = ThemeProvider()._get_site_notification(
            site_notification_cookie_value='test_id-1-False'
        )

        assert get_note[0] is note
        assert get_note[1] == 'test_id-2-False'


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

    @patch('allura.lib.plugin.datetime', autospec=True)
    def test_set_password_sets_last_updated(self, dt_mock):
        user = Mock()
        user.__ming__ = Mock()
        user.last_password_updated = None
        self.provider.set_password(user, None, 'new')
        assert_equal(user.last_password_updated, dt_mock.utcnow.return_value)

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
        with audits('Account enabled', user=True, actor='test-admin'):
            self.provider.enable_user(user)
            ThreadLocalORMSession.flush_all()
        assert_equal(user.disabled, False)

    def test_disable_user(self):
        user = Mock(disabled=False, __ming__=Mock(), is_anonymous=lambda: False, _id=ObjectId())
        c.user = Mock(username='test-admin')
        with audits('Account disabled', user=True, actor='test-admin'):
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
