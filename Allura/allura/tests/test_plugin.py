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

from functools import partial
from nose.tools import assert_equals, assert_raises, assert_is_none, assert_is
from mock import Mock, MagicMock, patch
from formencode import Invalid
from datetime import timedelta

from allura import model as M
from allura.lib.utils import TruthyCallable
from allura.lib.plugin import ProjectRegistrationProvider
from allura.lib.plugin import ThemeProvider
from allura.lib.exceptions import ProjectConflict, ProjectShortnameInvalid


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
        assert_raises(ProjectShortnameInvalid, v, 'not valid', neighborhood=nbhd)
        assert_raises(ProjectShortnameInvalid, v, 'this-is-valid-but-too-long', neighborhood=nbhd)
        assert_raises(ProjectShortnameInvalid, v, 'this is invalid and too long', neighborhood=nbhd)
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
        response.set_cookie.assert_called_once_with('site-notification', 'deadbeef-2-False', max_age=timedelta(days=365))

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
        response.set_cookie.assert_called_once_with('site-notification', 'deadbeef-1-False', max_age=timedelta(days=365))

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.response')
    @patch('pylons.request')
    def test_get_site_notification_no_cookie(self, request, response, SiteNotification):
        note = SiteNotification.current.return_value
        note._id = 'deadbeef'
        note.impressions = 0
        request.cookies = {}
        assert_is(ThemeProvider().get_site_notification(), note)
        response.set_cookie.assert_called_once_with('site-notification', 'deadbeef-1-False', max_age=timedelta(days=365))

    @patch('allura.model.notification.SiteNotification')
    @patch('pylons.response')
    @patch('pylons.request')
    def test_get_site_notification_bad_cookie(self, request, response, SiteNotification):
        note = SiteNotification.current.return_value
        note._id = 'deadbeef'
        note.impressions = 0
        request.cookies = {'site-notification': 'deadbeef-1000-true-bad'}
        assert_is(ThemeProvider().get_site_notification(), note)
        response.set_cookie.assert_called_once_with('site-notification', 'deadbeef-1-False', max_age=timedelta(days=365))
