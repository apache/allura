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
from tg import tmpl_context as c
from webob import Request, exc
from bson import ObjectId
from ming.orm.ormsession import ThreadLocalORMSession
from mock import Mock, MagicMock, patch
import pytest

from allura import model as M
from allura.lib import plugin
from allura.lib import phone
from allura.lib import helpers as h
from allura.lib.utils import TruthyCallable
from allura.lib.plugin import ProjectRegistrationProvider
from allura.lib.plugin import ThemeProvider
from allura.lib.exceptions import ProjectConflict, ProjectShortnameInvalid
from allura.tests.decorators import audits
from allura.tests.exclude_from_rewrite_hook import ThemeProviderTestApp
from alluratest.controller import setup_basic_test, setup_global_objects


def setup_module(module):
    setup_basic_test()


class TestProjectRegistrationProvider:

    def setup_method(self, method):
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
        pytest.raises(ProjectShortnameInvalid, v,
                      'not valid', neighborhood=nbhd)
        pytest.raises(ProjectShortnameInvalid, v,
                      'this-is-valid-but-too-long', neighborhood=nbhd)
        pytest.raises(ProjectShortnameInvalid, v,
                      'this is invalid and too long', neighborhood=nbhd)
        pytest.raises(ProjectShortnameInvalid, v,
                      'end-dash-', neighborhood=nbhd)
        Project.query.get.return_value = Mock()
        pytest.raises(ProjectConflict, v, 'thisislegit', neighborhood=nbhd)


class TestProjectRegistrationProviderParseProjectFromUrl:

    def setup_method(self, method):
        setup_basic_test()
        ThreadLocalORMSession.close_all()
        setup_global_objects()
        self.provider = ProjectRegistrationProvider()
        self.parse = self.provider.project_from_url

    def test_empty_url(self):
        assert (None, 'Empty url') == self.parse(None)
        assert (None, 'Empty url') == self.parse('')
        assert (None, 'Empty url') == self.parse('/')

    def test_neighborhood_not_found(self):
        assert (None, 'Neighborhood not found') == self.parse('/nbhd/project')

    def test_project_not_found(self):
        assert (None, 'Project not found') == self.parse('/p/project')
        assert (None, 'Project not found') == self.parse('project')

    def test_ok_full(self):
        p = M.Project.query.get(shortname='test')
        adobe = M.Project.query.get(shortname='adobe-1')
        assert (p, None) == self.parse('p/test')
        assert (p, None) == self.parse('/p/test')
        assert (p, None) == self.parse('/p/test/tickets/1')
        assert (p, None) == self.parse('http://localhost:8080/p/test/tickets/1')
        assert (adobe, None) == self.parse('/adobe/adobe-1/')

    def test_only_shortname_multiple_projects_matched(self):
        adobe_n = M.Neighborhood.query.get(url_prefix='/adobe/')
        M.Project(shortname='test', neighborhood_id=adobe_n._id)
        ThreadLocalORMSession.flush_all()
        assert (None, 'Too many matches for project: 2') == self.parse('test')

    def test_only_shortname_ok(self):
        p = M.Project.query.get(shortname='test')
        adobe = M.Project.query.get(shortname='adobe-1')
        assert (p, None) == self.parse('test')
        assert (adobe, None) == self.parse('adobe-1')

    def test_subproject(self):
        p = M.Project.query.get(shortname='test/sub1')
        assert (p, None) == self.parse('p/test/sub1')
        assert (p, None) == self.parse('p/test/sub1/something')
        assert (p, None) == self.parse('http://localhost:8080/p/test/sub1')
        assert (p, None) == self.parse('http://localhost:8080/p/test/sub1/something')

    def test_subproject_not_found(self):
        p = M.Project.query.get(shortname='test')
        assert (p, None) == self.parse('http://localhost:8080/p/test/not-a-sub')


class UserMock:
    def __init__(self):
        self.tool_data = {}
        self._projects = []
        self.username = 'usermock'

    def get_tool_data(self, tool, key):
        return self.tool_data.get(tool, {}).get(key, None)

    def set_tool_data(self, tool, **kw):
        d = self.tool_data.setdefault(tool, {})
        d.update(kw)

    def set_projects(self, projects):
        self._projects = projects

    def my_projects_by_role_name(self, role):
        return self._projects


class TestProjectRegistrationProviderPhoneVerification:

    def setup_method(self, method):
        self.p = ProjectRegistrationProvider()
        self.user = UserMock()
        self.nbhd = MagicMock()

    def test_phone_verified_disabled(self):
        with h.push_config(tg.config, **{'project.verify_phone': 'false'}):
            assert self.p.phone_verified(self.user, self.nbhd)

    @patch.object(plugin.security, 'has_access', autospec=True)
    def test_phone_verified_admin(self, has_access):
        has_access.return_value.return_value = True
        with h.push_config(tg.config, **{'project.verify_phone': 'true'}):
            assert self.p.phone_verified(self.user, self.nbhd)

    @patch.object(plugin.security, 'has_access', autospec=True)
    def test_phone_verified_project_admin(self, has_access):
        has_access.return_value.return_value = False
        with h.push_config(tg.config, **{'project.verify_phone': 'true'}):
            self.user.set_projects([Mock()])
            assert not self.p.phone_verified(self.user, self.nbhd)
            self.user.set_projects([Mock(neighborhood_id=self.nbhd._id)])
            assert self.p.phone_verified(self.user, self.nbhd)

    @patch.object(plugin.security, 'has_access', autospec=True)
    def test_phone_verified(self, has_access):
        has_access.return_value.return_value = False
        with h.push_config(tg.config, **{'project.verify_phone': 'true'}):
            assert not self.p.phone_verified(self.user, self.nbhd)
            self.user.set_tool_data('phone_verification', number_hash='123')
            assert self.p.phone_verified(self.user, self.nbhd)

    @patch.object(plugin, 'g')
    def test_verify_phone_disabled(self, g):
        g.phone_service = Mock(spec=phone.PhoneService)
        with h.push_config(tg.config, **{'project.verify_phone': 'false'}):
            result = self.p.verify_phone(self.user, '12345')
            assert not g.phone_service.verify.called
            assert result == {'status': 'ok'}

    @patch.object(plugin, 'g')
    def test_verify_phone(self, g):
        g.phone_service = Mock(spec=phone.PhoneService)
        with h.push_config(tg.config, **{'project.verify_phone': 'true'}):
            result = self.p.verify_phone(self.user, '123 45 45')
            g.phone_service.verify.assert_called_once_with('1234545')
            assert result == g.phone_service.verify.return_value

    @patch.object(plugin, 'g')
    def test_check_phone_verification_disabled(self, g):
        g.phone_service = Mock(spec=phone.PhoneService)
        with h.push_config(tg.config, **{'project.verify_phone': 'false'}):
            result = self.p.check_phone_verification(
                self.user, 'request-id', '1111', 'hash')
            assert not g.phone_service.check.called
            assert result == {'status': 'ok'}

    @patch.object(plugin.h, 'auditlog_user', autospec=True)
    @patch.object(plugin, 'g')
    def test_check_phone_verification_fail(self, g, audit):
        g.phone_service = Mock(spec=phone.PhoneService)
        with h.push_config(tg.config, **{'project.verify_phone': 'true'}):
            result = self.p.check_phone_verification(
                self.user, 'request-id', '1111', 'hash')
            g.phone_service.check.assert_called_once_with(
                'request-id', '1111')
            assert result == g.phone_service.check.return_value
            assert (
                self.user.get_tool_data('phone_verification', 'number_hash') ==
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
            assert (
                self.user.get_tool_data('phone_verification', 'number_hash') ==
                'hash')
            audit.assert_called_once_with(
                'Phone verification succeeded. Hash: hash', user=self.user)

    @patch.object(plugin, 'g')
    def test_verify_phone_max_limit_not_reached(self, g):
        g.phone_service = Mock(spec=phone.PhoneService)
        user = UserMock()
        user.is_anonymous = lambda: True
        with h.push_config(tg.config, **{'project.verify_phone': 'true', 'phone.attempts_limit': '5'}):
            for i in range(1, 3):
                result = self.p.verify_phone(user, '123 45 45')
                assert result == g.phone_service.verify.return_value
            assert 2 == g.phone_service.verify.call_count

    @patch.object(plugin, 'g')
    def test_verify_phone_max_limit_reached(self, g):
        g.phone_service = Mock(spec=phone.PhoneService)
        user = UserMock()
        user.is_anonymous = lambda: True
        with h.push_config(tg.config, **{'project.verify_phone': 'true', 'phone.attempts_limit': '5'}):
            for i in range(1, 7):
                result = self.p.verify_phone(user, '123 45 45')
                if i > 5:
                    assert result == {'status': 'error', 'error': 'Maximum phone verification attempts reached.'}
                else:
                    assert result == g.phone_service.verify.return_value
            assert 5 == g.phone_service.verify.call_count


class TestThemeProvider:

    @patch('allura.app.g')
    @patch('allura.lib.plugin.g')
    def test_app_icon_str(self, plugin_g, app_g):
        plugin_g.entry_points = {'tool': {'testapp': ThemeProviderTestApp}}
        app_icon = ThemeProvider().app_icon_url('testapp', 24)
        other = app_g.theme_href.return_value
        assert app_icon == other

        app_g.theme_href.assert_called_with('images/testapp_24.png')

    @patch('allura.lib.plugin.g')
    def test_app_icon_str_invalid(self, g):
        g.entry_points = {'tool': {'testapp': Mock()}}
        assert ThemeProvider().app_icon_url('invalid', 24) is None

    @patch('allura.app.g')
    def test_app_icon_app(self, g):
        app = ThemeProviderTestApp(None, None)
        assert ThemeProvider().app_icon_url(app, 24) == \
            g.theme_href.return_value
        g.theme_href.assert_called_with('images/testapp_24.png')


class TestThemeProvider_notifications:

    Provider = ThemeProvider

    @patch('allura.lib.plugin.c', MagicMock())
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response')
    @patch('tg.request')
    def test_get_site_notification_no_note(self, request, response, SiteNotification):
        SiteNotification.actives.return_value = []
        assert self.Provider().get_site_notification() is None
        assert not response.set_cookie.called

    @patch('allura.lib.plugin.c', MagicMock())
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response')
    @patch('tg.request')
    def test_get_site_notification_closed(self, request, response, SiteNotification):
        note = MagicMock()
        note._id = 'deadbeef'
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        SiteNotification.actives.return_value = [note]
        request.cookies = {'site-notification': 'deadbeef-1-true'}
        assert self.Provider().get_site_notification() is None
        assert not response.set_cookie.called

    @patch('allura.lib.plugin.c', MagicMock())
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response')
    @patch('tg.request')
    def test_get_site_notification_impressions_over(self, request, response, SiteNotification):
        note = MagicMock()
        note._id = 'deadbeef'
        note.impressions = 2
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        SiteNotification.actives.return_value = [note]
        request.cookies = {'site-notification': 'deadbeef-3-false'}
        assert self.Provider().get_site_notification() is None
        assert not response.set_cookie.called

    @patch('allura.lib.plugin.c', MagicMock())
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response')
    @patch('tg.request')
    def test_get_site_notification_impressions_under(self, request, response, SiteNotification):
        note = MagicMock()
        note._id = 'deadbeef'
        note.impressions = 2
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        SiteNotification.actives.return_value = [note]
        request.cookies = {'site-notification': 'deadbeef-1-false'}
        request.environ['beaker.session'].secure = False

        assert self.Provider().get_site_notification() is note
        response.set_cookie.assert_called_once_with(
            'site-notification', 'deadbeef-2-False', max_age=dt.timedelta(days=365), secure=False)

    @patch('allura.lib.plugin.c', MagicMock())
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response')
    @patch('tg.request')
    def test_get_site_notification_impressions_persistent(self, request, response, SiteNotification):
        note = MagicMock()
        note._id = 'deadbeef'
        note.impressions = 0
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        SiteNotification.actives.return_value = [note]
        request.cookies = {'site-notification': 'deadbeef-1000-false'}
        assert self.Provider().get_site_notification() is note

    @patch('allura.lib.plugin.c', MagicMock())
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response')
    @patch('tg.request')
    def test_get_site_notification_new_notification(self, request, response, SiteNotification):
        note = MagicMock()
        note._id = 'deadbeef'
        note.impressions = 1
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        SiteNotification.actives.return_value = [note]
        request.cookies = {'site-notification': '0ddba11-1000-true'}
        request.environ['beaker.session'].secure = False

        assert self.Provider().get_site_notification() is note
        response.set_cookie.assert_called_once_with(
            'site-notification', 'deadbeef-1-False', max_age=dt.timedelta(days=365), secure=False)

    @patch('allura.lib.plugin.c', MagicMock())
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response')
    @patch('tg.request')
    def test_get_site_notification_no_cookie(self, request, response, SiteNotification):
        note = MagicMock()
        note._id = 'deadbeef'
        note.impressions = 0
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        SiteNotification.actives.return_value = [note]
        request.cookies = {}
        request.environ['beaker.session'].secure = False
        assert self.Provider().get_site_notification() is note
        response.set_cookie.assert_called_once_with(
            'site-notification', 'deadbeef-1-False', max_age=dt.timedelta(days=365), secure=False)

    @patch('allura.lib.plugin.c', MagicMock())
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response')
    @patch('tg.request')
    def test_get_site_notification_bad_cookie(self, request, response, SiteNotification):
        note = MagicMock()
        note._id = 'deadbeef'
        note.impressions = 0
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        SiteNotification.actives.return_value = [note]
        request.cookies = {'site-notification': 'deadbeef-1000-true-bad'}
        request.environ['beaker.session'].secure = False

        assert self.Provider().get_site_notification() is note
        response.set_cookie.assert_called_once_with(
            'site-notification', 'deadbeef-1-False', max_age=dt.timedelta(days=365), secure=False)

    @patch('allura.lib.plugin.c')
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response', MagicMock())
    @patch('tg.request', MagicMock())
    def test_get_site_notification_with_role(self, SiteNotification, c):
        note = MagicMock()
        note.user_role = 'Test'
        note.page_regex = None
        note.page_tool_type = None
        note.impressions = 10
        SiteNotification.actives.return_value = [note]
        projects = c.user.my_projects_by_role_name

        c.user.is_anonymous.return_value = True
        assert self.Provider().get_site_notification() is None

        c.user.is_anonymous.return_value = False
        projects.return_value = []
        assert self.Provider().get_site_notification() is None

        projects.return_value = [Mock()]
        projects.return_value[0].is_user_project = True
        assert self.Provider().get_site_notification() is None

        projects.return_value[0].is_user_project = False
        assert self.Provider().get_site_notification() is note

        projects.projects.return_value = [Mock(), Mock()]
        assert self.Provider().get_site_notification() is note

    @patch('allura.lib.plugin.c', MagicMock())
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response', MagicMock())
    @patch('tg.request', MagicMock())
    def test_get_site_notification_without_role(self, SiteNotification):
        note = MagicMock()
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        note.impressions = 10
        SiteNotification.actives.return_value = [note]
        assert self.Provider().get_site_notification() is note

    @patch('allura.lib.plugin.c', MagicMock())
    @patch('re.search')
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response', MagicMock())
    @patch('tg.request', MagicMock())
    def test_get_site_notification_with_page_regex(self, SiteNotification, search):
        note = MagicMock()
        note.user_role = None
        note.page_regex = 'test'
        note.page_tool_type = None
        note.impressions = 10
        SiteNotification.actives.return_value = [note]

        search.return_value = True
        assert self.Provider().get_site_notification() is note

        search.return_value = None
        assert self.Provider().get_site_notification() is None

    @patch('allura.lib.plugin.c')
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response', MagicMock())
    @patch('tg.request', MagicMock())
    def test_get_site_notification_with_page_tool_type(self, SiteNotification, c):
        note = MagicMock()
        note.user_role = None
        note.page_regex = None
        note.page_tool_type.lower.return_value = 'test1'
        note.impressions = 10
        SiteNotification.actives.return_value = [note]
        c.app = Mock()
        c.app.config.tool_name.lower.return_value = 'test1'
        assert self.Provider().get_site_notification() is note

        c.app.config.tool_name.lower.return_value = 'test2'
        assert self.Provider().get_site_notification() is None

        c.app = None
        assert self.Provider().get_site_notification() is None

    @patch('allura.lib.plugin.c')
    @patch('tg.request')
    @patch('allura.model.notification.SiteNotification')
    @patch('tg.response', MagicMock())
    def test_get_site_notification_with_page_tool_type_page_regex(self, SiteNotification, request, c):
        note = MagicMock()
        note.user_role = None
        note.page_regex = 'test'
        note.page_tool_type.lower.return_value = 'test1'
        note.impressions = 10
        SiteNotification.actives.return_value = [note]
        c.app = Mock()

        request.path_qs = 'ttt'
        c.app.config.tool_name.lower.return_value = 'test2'
        assert self.Provider().get_site_notification() is None

        request.path_qs = 'test'
        assert self.Provider().get_site_notification() is None

        request.path_qs = 'ttt'
        c.app.config.tool_name.lower.return_value = 'test1'
        assert self.Provider().get_site_notification() is None

        request.path_qs = 'test'
        assert self.Provider().get_site_notification() is note

        c.app = None
        assert self.Provider().get_site_notification() is None

        request.path_qs = 'ttt'
        assert self.Provider().get_site_notification() is None

    @patch('allura.model.notification.SiteNotification')
    def test_get__site_notification(self, SiteNotification):
        note = MagicMock()
        note._id = 'testid'
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        note.impressions = 10
        SiteNotification.actives.return_value = [note]
        get_note = self.Provider()._get_site_notification()

        assert isinstance(get_note, tuple)
        assert len(get_note) == 2
        assert get_note[0] is note
        assert get_note[1] == 'testid-1-False'

    @patch('allura.model.notification.SiteNotification')
    def test_get__site_notification_multiple(self, SiteNotification):
        note1 = MagicMock(name='note1')
        note1._id = 'test1'
        note1.user_role = None
        note1.page_regex = 'this-will-not-match'
        note1.page_tool_type = None
        note1.impressions = 10
        note2 = MagicMock(name='note2')
        note2._id = 'test2'
        note2.user_role = None
        note2.page_regex = None
        note2.page_tool_type = None
        note2.impressions = 10
        note3 = MagicMock(name='note3')
        note3._id = 'test3'
        note3.user_role = None
        note3.page_regex = None
        note3.page_tool_type = None
        note3.impressions = 10
        SiteNotification.actives.return_value = [note1, note2, note3]
        get_note = self.Provider()._get_site_notification()

        assert isinstance(get_note, tuple)
        assert len(get_note) == 2
        assert get_note[0] == note2
        assert get_note[1] == 'test2-1-False'

        # and with a cookie set
        get_note = self.Provider()._get_site_notification(
            site_notification_cookie_value='test2-3-True_test3-0-False'
        )

        assert isinstance(get_note, tuple)
        assert len(get_note) == 2
        assert get_note[0] == note3
        assert get_note[1] == 'test2-3-True_test3-1-False'

    @patch('allura.model.notification.SiteNotification')
    def test_get_site_notifications_with_api_cookie(self, SiteNotification):
        note = MagicMock()
        note._id = 'testid'
        note.user_role = None
        note.page_regex = None
        note.page_tool_type = None
        note.impressions = 10
        SiteNotification.actives.return_value = [note]
        get_note = self.Provider()._get_site_notification(
            site_notification_cookie_value='testid-1-False'
        )

        assert get_note[0] is note
        assert get_note[1] == 'testid-2-False'


class TestLocalAuthenticationProvider:

    def setup_method(self, method):
        setup_basic_test()
        ThreadLocalORMSession.close_all()
        setup_global_objects()
        self.provider = plugin.LocalAuthenticationProvider(Request.blank('/'))

    def test_password_encoder(self):
        # Verify salt
        ep = self.provider._encode_password
        assert ep('test_pass') != ep('test_pass')
        assert ep('test_pass', '0000') == ep('test_pass', '0000')
        assert ep('test_pass', '0000') == 'sha2560000j7pRjKKZ5L8G0jScZKja9ECmYF2zBV82Mi+E3wkop30='

    def test_set_password_with_old_password(self):
        user = Mock()
        user.__ming__ = Mock()
        self.provider.validate_password = lambda u, p: False
        self.provider._encode_password = Mock()
        pytest.raises(
            exc.HTTPUnauthorized,
            self.provider.set_password, user, 'old', 'new')
        assert self.provider._encode_password.call_count == 0

        self.provider.validate_password = lambda u, p: True
        self.provider.set_password(user, 'old', 'new')
        self.provider._encode_password.assert_called_once_with('new')

    @patch('allura.lib.plugin.datetime', autospec=True)
    def test_set_password_sets_last_updated(self, dt_mock):
        user = Mock()
        user.__ming__ = Mock()
        user.last_password_updated = None
        self.provider.set_password(user, None, 'new')
        assert user.last_password_updated == dt_mock.utcnow.return_value

    def test_get_last_password_updated_not_set(self):
        user = Mock()
        user._id = ObjectId()
        user.last_password_updated = None
        user.reg_date = None
        upd = self.provider.get_last_password_updated(user)
        gen_time = dt.datetime.utcfromtimestamp(
            calendar.timegm(user._id.generation_time.utctimetuple()))
        assert upd == gen_time

    def test_get_last_password_updated(self):
        user = Mock()
        user.last_password_updated = dt.datetime(2014, 6, 4, 13, 13, 13)
        upd = self.provider.get_last_password_updated(user)
        assert upd == user.last_password_updated

    def test_enable_user(self):
        user = Mock(disabled=True, __ming__=Mock(), is_anonymous=lambda: False, _id=ObjectId())
        c.user = Mock(username='test-admin')
        with audits('Account enabled', user=True, actor='test-admin'):
            self.provider.enable_user(user)
            ThreadLocalORMSession.flush_all()
        assert user.disabled is False

    def test_disable_user(self):
        user = Mock(disabled=False, __ming__=Mock(), is_anonymous=lambda: False, _id=ObjectId())
        c.user = Mock(username='test-admin')
        with audits('Account disabled', user=True, actor='test-admin'):
            self.provider.disable_user(user)
            ThreadLocalORMSession.flush_all()
        assert user.disabled is True

    def test_login_details_from_auditlog(self):
        user = M.User(username='asfdasdf')

        assert (self.provider.login_details_from_auditlog(M.AuditLog(message='')) ==
                None)

        detail = self.provider.login_details_from_auditlog(M.AuditLog(message='IP Address: 1.2.3.4\nFoo', user=user))
        assert detail.user_id == user._id
        assert detail.ip == '1.2.3.4'
        assert detail.ua is None

        detail = self.provider.login_details_from_auditlog(M.AuditLog(message='Foo\nIP Address: 1.2.3.4\nFoo', user=user))
        assert detail.ip == '1.2.3.4'
        assert detail.ua is None

        assert (self.provider.login_details_from_auditlog(M.AuditLog(
            message='blah blah IP Address: 1.2.3.4\nFoo', user=user)) ==
            None)

        detail = self.provider.login_details_from_auditlog(M.AuditLog(
            message='User-Agent: Mozilla/Firefox\nFoo', user=user))
        assert detail.ip is None
        assert detail.ua == 'Mozilla/Firefox'

        detail = self.provider.login_details_from_auditlog(M.AuditLog(
            message='IP Address: 1.2.3.4\nUser-Agent: Mozilla/Firefox\nFoo', user=user))
        assert detail.ip == '1.2.3.4'
        assert detail.ua == 'Mozilla/Firefox'

    def test_get_login_detail(self):
        user = M.User(username='foobarbaz')
        detail = self.provider.get_login_detail(Request.blank('/'), user)
        assert detail.user_id == user._id
        assert detail.ip is None
        assert detail.ua is None

        detail = self.provider.get_login_detail(Request.blank('/',
                                                              headers={'User-Agent': 'mybrowser'},
                                                              environ={'REMOTE_ADDR': '3.3.3.3'}),
                                                user)
        assert detail.user_id == user._id
        assert detail.ip == '3.3.3.3'
        assert detail.ua == 'mybrowser'


class TestAuthenticationProvider:

    def setup_method(self, method):
        setup_basic_test()
        self.provider = plugin.AuthenticationProvider(Request.blank('/'))
        self.pwd_updated = dt.datetime.utcnow() - dt.timedelta(days=100)
        self.provider.get_last_password_updated = lambda u: self.pwd_updated
        self.user = Mock()

    def test_is_password_expired_disabled(self):
        assert not self.provider.is_password_expired(self.user)

    def test_is_password_expired_days(self):
        with h.push_config(tg.config, **{'auth.pwdexpire.days': '180'}):
            assert not self.provider.is_password_expired(self.user)
        with h.push_config(tg.config, **{'auth.pwdexpire.days': '90'}):
            assert self.provider.is_password_expired(self.user)

    def test_is_password_expired_before(self):
        before = dt.datetime.utcnow() - dt.timedelta(days=180)
        before = calendar.timegm(before.timetuple())
        with h.push_config(tg.config, **{'auth.pwdexpire.before': str(before)}):
            assert not self.provider.is_password_expired(self.user)

        before = dt.datetime.utcnow() - dt.timedelta(days=1)
        before = calendar.timegm(before.timetuple())
        with h.push_config(tg.config, **{'auth.pwdexpire.before': str(before)}):
            assert self.provider.is_password_expired(self.user)
