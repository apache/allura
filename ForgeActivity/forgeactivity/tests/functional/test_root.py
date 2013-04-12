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

from mock import patch
from tg import config

from nose.tools import assert_equal

from alluratest.controller import TestController
from allura.tests import decorators as td


class TestActivityController(TestController):
    def setUp(self, *args, **kwargs):
        super(TestActivityController, self).setUp(*args, **kwargs)
        self._enabled = config.get('activitystream.enabled', 'false')
        config['activitystream.enabled'] = 'true'

    def tearDown(self, *args, **kwargs):
        super(TestActivityController, self).tearDown(*args, **kwargs)
        config['activitystream.enabled'] = self._enabled

    def test_index(self):
        resp = self.app.get('/activity/')
        assert 'No activity to display.' in resp

    def test_index_disabled(self):
        config['activitystream.enabled'] = 'false'
        resp = self.app.get('/activity/', status=404)

    def test_index_override(self):
        config['activitystream.enabled'] = 'false'
        self.app.cookies['activitystream.enabled'] = 'true'
        resp = self.app.get('/activity/')
        assert 'No activity to display.' in resp

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    def test_follow_user(self):
        resp = self.app.get('/u/test-user-1/activity/follow?follow=True')
        assert 'You are now following Test User 1' in resp, resp

    @td.with_tool('u/test-admin', 'activity')
    @td.with_user_project('test-admin')
    @patch('forgeactivity.main.g.director')
    def test_viewing_own_user_project(self, director):
        resp = self.app.get('/u/test-admin/activity/')
        assert director.get_timeline.call_count == 1
        assert director.get_timeline.call_args[0][0].username == 'test-admin'
        assert director.get_timeline.call_args[1]['actor_only'] == False

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    @patch('forgeactivity.main.g.director')
    def test_viewing_other_user_project(self, director):
        resp = self.app.get('/u/test-user-1/activity/')
        assert director.get_timeline.call_count == 1
        assert director.get_timeline.call_args[0][0].username == 'test-user-1'
        assert director.get_timeline.call_args[1]['actor_only'] == True

    @td.with_tool('test', 'activity')
    @patch('forgeactivity.main.g.director')
    def test_viewing_project_activity(self, director):
        resp = self.app.get('/p/test/activity/')
        assert director.get_timeline.call_count == 1
        assert director.get_timeline.call_args[0][0].shortname == 'test'
        assert director.get_timeline.call_args[1]['actor_only'] == False
