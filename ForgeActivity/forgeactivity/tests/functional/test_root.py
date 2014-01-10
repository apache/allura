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
from textwrap import dedent
from tg import config

import dateutil.parser
from nose.tools import assert_equal
from pylons import app_globals as g

from allura import model as M
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
        self.app.get('/activity/', status=404)

    def test_index_override(self):
        config['activitystream.enabled'] = 'false'
        self.app.cookies['activitystream.enabled'] = 'true'
        resp = self.app.get('/activity/')
        assert 'No activity to display.' in resp

    @td.with_tool('test', 'activity')
    @patch('forgeactivity.main.g.director')
    def test_index_html(self, director):
        from activitystream.storage.base import StoredActivity
        from bson import ObjectId
        director.get_timeline.return_value = [StoredActivity(**{
            "_id": ObjectId("529fa331033c5e6406d8b338"),
            "obj": {
                "activity_extras": {
                    "allura_id": "Post:971389ad979eaafa658beb807bf4629d30f5f642.tickets@test.p.sourceforge.net",
                    "summary": "Just wanted to leave a comment on this..."
                },
                "activity_url": "/p/test/tickets/_discuss/thread/08e74efd/ed7c/",
                "activity_name": "a comment"
            },
            "target": {
                "activity_extras": {
                    "allura_id": "Ticket:529f57a6033c5e5985db2efa",
                    "summary": "Make activitystream timeline look better"
                },
                "activity_url": "/p/test/tickets/34/",
                "activity_name": "ticket #34"
            },
            "actor": {
                "activity_extras": {
                    "icon_url": "/u/test-admin/user_icon",
                    "allura_id": "User:521f96cb033c5e2587adbdff"
                },
                "activity_url": "/u/test-admin/",
                "activity_name": "Administrator 1",
                "node_id": "User:521f96cb033c5e2587adbdff"
            },
            "verb": "posted",
            "published": dateutil.parser.parse("2013-12-04T21:48:19.817"),
            "score": 1386193699,
            "node_id": "Project:527a6584033c5e62126f5a60",
            "owner_id": "Project:527a6584033c5e62126f5a60"
        })]
        r = self.app.get('/p/test/activity/')
        timeline = r.html.find('ul', 'timeline')
        assert_equal(1, len(timeline.findAll('li')))
        activity = timeline.find('li')
        assert_equal(activity.time['title'], "2013-12-04 21:48:19")
        h1 = """\
        <h1>
        <img src="/u/test-admin/user_icon" alt="Administrator 1" title="Administrator 1" class="emboss x32 avatar" />
        <a href="/u/test-admin/">
         Administrator 1
        </a>
        posted
        <a href="/p/test/tickets/_discuss/thread/08e74efd/ed7c/">
         a comment
        </a>
        on
        <a href="/p/test/tickets/34/">
         ticket #34
        </a>
        </h1>
        """
        assert_equal(dedent(h1), activity.h1.prettify())
        p = """\
        <p>
        Just wanted to leave a comment on this...
        </p>
        """
        assert_equal(dedent(p), activity.p.prettify())

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    def test_follow_user(self):
        resp = self.app.get('/u/test-user-1/activity/follow?follow=True')
        assert 'You are now following Test User 1' in resp, resp

    @td.with_tool('u/test-admin', 'activity')
    @td.with_user_project('test-admin')
    @patch('forgeactivity.main.g.director')
    def test_viewing_own_user_project(self, director):
        self.app.get('/u/test-admin/activity/')
        assert director.get_timeline.call_count == 1
        assert director.get_timeline.call_args[0][0].username == 'test-admin'
        assert director.get_timeline.call_args[1]['actor_only'] == False

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    @patch('forgeactivity.main.g.director')
    def test_viewing_other_user_project(self, director):
        self.app.get('/u/test-user-1/activity/')
        assert director.get_timeline.call_count == 1
        assert director.get_timeline.call_args[0][0].username == 'test-user-1'
        assert director.get_timeline.call_args[1]['actor_only'] == True

    @td.with_tool('test', 'activity')
    @patch('forgeactivity.main.g.director')
    def test_viewing_project_activity(self, director):
        self.app.get('/p/test/activity/')
        assert director.get_timeline.call_count == 1
        assert director.get_timeline.call_args[0][0].shortname == 'test'
        assert director.get_timeline.call_args[1]['actor_only'] == False

    @td.with_tracker
    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    def test_background_aggregation(self):
        self.app.get('/u/test-admin/activity/follow?follow=True',
                     extra_environ=dict(username='test-user-1'))
        # new ticket, creates activity
        d = {'ticket_form.summary': 'New Ticket'}
        self.app.post('/bugs/save_ticket', params=d)
        orig_create_timeline = g.director.aggregator.create_timeline
        with patch.object(g.director.aggregator, 'create_timeline') as create_timeline:
            create_timeline.side_effect = orig_create_timeline
            M.MonQTask.run_ready()
            # 3 aggregations: 1 actor, 1 follower, 1 project
            assert_equal(create_timeline.call_count, 3)
            create_timeline.reset_mock()
            self.app.get('/u/test-admin/activity/')
            self.app.get('/u/test-user-1/activity/')
            assert_equal(create_timeline.call_count, 0)
