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

from textwrap import dedent

from mock import patch
from tg import config
from bson import ObjectId
import dateutil.parser
from tg import app_globals as g
from activitystream.storage.mingstorage import Activity
from ming.odm import ThreadLocalODMSession

from allura import model as M
from alluratest.controller import TestController
from allura.tests import decorators as td


class TestActivityController(TestController):

    def setup_method(self, method, *args, **kwargs):
        super().setup_method(method, *args, **kwargs)
        self._enabled = config.get('activitystream.enabled', 'false')
        config['activitystream.enabled'] = 'true'

    def teardown_method(self, method, *args, **kwargs):
        super().teardown_method(method, *args, **kwargs)
        config['activitystream.enabled'] = self._enabled

    def test_index(self):
        resp = self.app.get('/activity/')
        assert 'No activity to display.' in resp, resp

    def test_index_disabled(self):
        config['activitystream.enabled'] = 'false'
        self.app.get('/activity/', status=404)

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    def test_anon_read(self):
        r = self.app.get('/u/test-user-1',
                         extra_environ={'username': '*anonymous'}).follow()
        assert r.html.select('div.profile-section.tools a[href="/u/test-user-1/activity/"]'),\
            'No Activity tool in top nav'

    @td.with_tool('test', 'activity')
    @patch('forgeactivity.main.g.director')
    def test_index_html(self, director):
        director.get_timeline.return_value = [Activity(**{
            "_id": ObjectId("529fa331033c5e6406d8b338"),
            "obj": {
                "activity_extras": {
                    "summary": "Just wanted to leave a comment on this..."
                },
                "activity_url": "/p/test/tickets/34/?limit=25#ed7c",
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
        assert 1 == len(timeline.findAll('li'))
        activity = timeline.find('li')
        assert activity.time['title'] == "2013-12-04 21:48:19"
        h1 = """\
        <h1>
         <img alt="Administrator 1" class="emboss x32 avatar" src="/u/test-admin/user_icon" title="Administrator 1"/>
         <a href="/u/test-admin/profile/">
          Administrator 1
         </a>
         posted
         <a href="/p/test/tickets/34/?limit=25#ed7c">
          a comment
         </a>
         on
         <a href="/p/test/tickets/34/">
          ticket #34
         </a>
        </h1>
        """
        assert dedent(h1) == activity.h1.prettify()
        p = """\
        <p>
         Just wanted to leave a comment on this...
        </p>
        """
        assert dedent(p) == activity.p.prettify()

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    def test_follow_user(self):
        resp = self.app.post(
            '/u/test-user-1/activity/follow', {'follow': 'True'})
        assert 'You are now following Test User 1' in resp, resp

    @td.with_tool('u/test-admin', 'activity')
    @td.with_user_project('test-admin')
    @patch('forgeactivity.main.g.director')
    def test_viewing_own_user_project(self, director):
        self.app.get('/u/test-admin/activity/')
        assert director.get_timeline.call_count == 1
        assert director.get_timeline.call_args[0][0].username == 'test-admin'
        assert director.get_timeline.call_args[1]['actor_only'] is False

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    @patch('forgeactivity.main.g.director')
    def test_viewing_other_user_project(self, director):
        self.app.get('/u/test-user-1/activity/')
        assert director.get_timeline.call_count == 1
        assert director.get_timeline.call_args[0][0].username == 'test-user-1'
        assert director.get_timeline.call_args[1]['actor_only'] is True

    @td.with_tool('test', 'activity')
    @patch('forgeactivity.main.g.director')
    def test_viewing_project_activity(self, director):
        self.app.get('/p/test/activity/')
        assert director.get_timeline.call_count == 1
        assert director.get_timeline.call_args[0][0].shortname == 'test'
        assert director.get_timeline.call_args[1]['actor_only'] is False

    @td.with_tracker
    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    def test_background_aggregation(self):
        self.app.post('/u/test-admin/activity/follow', {'follow': 'true'},
                      extra_environ=dict(username='test-user-1'))
        # new ticket, creates activity
        d = {'ticket_form.summary': 'New Ticket'}
        self.app.post('/bugs/save_ticket', params=d)
        orig_create_timeline = g.director.aggregator.create_timeline
        with patch.object(g.director.aggregator, 'create_timeline') as \
                create_timeline:
            create_timeline.side_effect = orig_create_timeline
            M.MonQTask.run_ready()
            # 3 aggregations: 1 actor, 1 follower, 1 project
            assert create_timeline.call_count == 3
            create_timeline.reset_mock()
            self.app.get('/u/test-admin/activity/')
            self.app.get('/u/test-user-1/activity/')
            assert create_timeline.call_count == 0

    @td.with_tool('test', 'activity')
    @patch('forgeactivity.main.g.director')
    def test_feed_rss_project(self, director):
        director.get_timeline.return_value = [Activity(**{
            "_id": ObjectId("529fa331033c5e6406d8b338"),
            "obj": {
                "activity_extras": {
                    "summary": "Just wanted to leave a comment on this..."
                },
                "activity_url": "/p/test/unicode•º/?limit=25#ed7c",
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
        r = self.app.get('/p/test/activity/feed.rss')
        timeline = r.xml.find('channel')
        assert 1 == len(timeline.findall('item'))
        activity = timeline.find('item')
        assert (activity.find('pubDate').text ==
                'Wed, 04 Dec 2013 21:48:19 -0000')
        assert (activity.find('title').text ==
                'Administrator 1 posted a comment on ticket #34')
        assert (activity.find('description').text ==
                'Just wanted to leave a comment on this...')
        assert (activity.find('guid').text ==
                'http://localhost/p/test/unicode•º/?limit=25#ed7c')
        assert (activity.find('link').text ==
                'http://localhost/p/test/unicode%E2%80%A2%C2%BA/?limit=25#ed7c')

    @td.with_tool('test', 'activity')
    @patch('forgeactivity.main.g.director')
    def test_feed_rss_project_verb_without_activity_name(self, director):
        director.get_timeline.return_value = [Activity(**{
            "obj": {
                "activity_extras": {},
                "activity_url": "/p/test/tickets/34/?limit=25#ed7c",
                "activity_name": "ticket #34"
            },
            "target": {},
            "actor": {
                "activity_name": "Administrator 1",
            },
            "verb": "created"
        })]

        r = self.app.get('/p/test/activity/feed.rss')
        timeline = r.xml.find('channel')
        assert 1 == len(timeline.findall('item'))
        activity = timeline.find('item')

        assert activity.find('title').text == 'Administrator 1 created ticket #34'

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    @patch('forgeactivity.main.g.director')
    def test_feed_rss_user(self, director):
        director.get_timeline.return_value = [Activity(**{
            "_id": ObjectId("529fa331033c5e6406d8b338"),
            "obj": {
                "activity_extras": {
                    "summary": "Just wanted to leave a comment on this..."
                },
                "activity_url": "/p/test/tickets/34/?limit=25#ed7c",
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
        r = self.app.get('/u/test-user-1/activity/feed.rss')
        timeline = r.xml.find('channel')
        assert 1 == len(timeline.findall('item'))
        activity = timeline.find('item')
        assert (activity.find('pubDate').text ==
                'Wed, 04 Dec 2013 21:48:19 -0000')
        assert (activity.find('title').text ==
                'Administrator 1 posted a comment on ticket #34')
        assert (activity.find('description').text ==
                'Just wanted to leave a comment on this...')
        assert (activity.find('link').text ==
                'http://localhost/p/test/tickets/34/?limit=25#ed7c')

    @td.with_tool('test', 'activity')
    @patch('forgeactivity.main.g.director')
    def test_feed_atom_project(self, director):
        director.get_timeline.return_value = [Activity(**{
            "_id": ObjectId("529fa331033c5e6406d8b338"),
            "obj": {
                "activity_extras": {
                    "summary": "Just wanted to leave a comment on this..."
                },
                "activity_url": "/p/test/tickets/34/?limit=25#ed7c",
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
        r = self.app.get('/p/test/activity/feed.atom')
        timeline = r.xml
        assert 1 == len(timeline.findall(
            '{http://www.w3.org/2005/Atom}entry'))
        activity = timeline.find('{http://www.w3.org/2005/Atom}entry')
        assert (
            activity.find('{http://www.w3.org/2005/Atom}published').text ==
            '2013-12-04T21:48:19Z')
        assert (
            activity.find('{http://www.w3.org/2005/Atom}title').text ==
            'Administrator 1 posted a comment on ticket #34')
        assert (
            activity.find('{http://www.w3.org/2005/Atom}summary').text ==
            'Just wanted to leave a comment on this...')
        assert (
            activity.find('{http://www.w3.org/2005/Atom}link').get('href') ==
            'http://localhost/p/test/tickets/34/?limit=25#ed7c')

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    @patch('forgeactivity.main.g.director')
    def test_feed_atom_user(self, director):
        director.get_timeline.return_value = [Activity(**{
            "_id": ObjectId("529fa331033c5e6406d8b338"),
            "obj": {
                "activity_extras": {
                    "summary": "Just wanted to leave a comment on this..."
                },
                "activity_url": "/p/test/tickets/34/?limit=25#ed7c",
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
        r = self.app.get('/u/test-user-1/activity/feed.atom')
        timeline = r.xml
        assert 1 == len(timeline.findall(
            '{http://www.w3.org/2005/Atom}entry'))
        activity = timeline.find('{http://www.w3.org/2005/Atom}entry')
        assert (
            activity.find('{http://www.w3.org/2005/Atom}published').text ==
            '2013-12-04T21:48:19Z')
        assert (
            activity.find('{http://www.w3.org/2005/Atom}title').text ==
            'Administrator 1 posted a comment on ticket #34')
        assert (
            activity.find('{http://www.w3.org/2005/Atom}summary').text ==
            'Just wanted to leave a comment on this...')
        assert (
            activity.find('{http://www.w3.org/2005/Atom}link').get('href') ==
            'http://localhost/p/test/tickets/34/?limit=25#ed7c')

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    def test_delete_item_denied(self):
        self.app.post('/u/test-user-1/activity/delete_item',
                      {'activity_id': str(ObjectId())},
                      status=403)

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    def test_delete_item_gone(self):
        self.app.post('/u/test-user-1/activity/delete_item',
                      {'activity_id': str(ObjectId())},
                      extra_environ={'username': 'root'},  # nbhd admin
                      status=410)

    @td.with_tool('u/test-user-1', 'activity')
    @td.with_user_project('test-user-1')
    def test_delete_item_success(self):
        activity_data = {
            "obj": {
                "activity_extras": {
                    "summary": "Sensitive private info, oops"
                },
                "activity_url": "/p/test/tickets/34/?limit=25#ed7c",
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
        }
        activity = Activity(**activity_data)
        activity2 = Activity(**dict(activity_data, node_id='Project:123', owner_id='User:456'))
        activity3 = Activity(**dict(activity_data, node_id='User:abc', owner_id='User:abc'))
        ThreadLocalODMSession.flush_all()
        activity_id = str(activity._id)
        assert Activity.query.find({'obj.activity_extras.summary': 'Sensitive private info, oops'}).count() == 3

        self.app.post('/u/test-user-1/activity/delete_item',
                      {'activity_id': activity_id},
                      extra_environ={'username': 'root'},  # nbhd admin
                      status=200)
        ThreadLocalODMSession.flush_all()

        assert Activity.query.find({'obj.activity_extras.summary': 'Sensitive private info, oops'}).count() == 0
