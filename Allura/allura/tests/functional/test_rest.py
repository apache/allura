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

from datetime import datetime, timedelta

from pylons import app_globals as g
import mock
from nose.tools import assert_equal, assert_in, assert_not_in
from ming.odm import ThreadLocalODMSession
from datatree import Node

from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase
from allura.lib import helpers as h
from allura.lib.exceptions import Invalid
from allura import model as M

from forgetracker.tracker_main import ForgeTrackerApp


class TestRestHome(TestRestApiBase):

    def test_bad_signature(self):
        r = self.api_post('/rest/p/test/wiki/', api_signature='foo')
        assert r.status_int == 403

    def test_bad_token(self):
        r = self.api_post('/rest/p/test/wiki/', api_key='foo')
        assert r.status_int == 403

    def test_bad_timestamp(self):
        r = self.api_post('/rest/p/test/wiki/',
                          api_timestamp=(datetime.utcnow() + timedelta(days=1)).isoformat())
        assert r.status_int == 403

    @mock.patch('allura.controllers.rest.M.OAuthAccessToken')
    @mock.patch('allura.controllers.rest.request')
    def test_bearer_token_non_ssl(self, request, OAuthAccessToken):
        request.params = {'access_token': 'foo'}
        request.scheme = 'http'
        r = self.api_post('/rest/p/test/wiki', access_token='foo')
        assert_equal(r.status_int, 403)
        assert_equal(OAuthAccessToken.query.get.call_count, 0)

    @mock.patch('allura.controllers.rest.M.OAuthAccessToken')
    @mock.patch('allura.controllers.rest.request')
    def test_bearer_token_non_bearer(self, request, OAuthAccessToken):
        request.params = {'access_token': 'foo'}
        request.scheme = 'https'
        access_token = OAuthAccessToken.query.get.return_value
        access_token.is_bearer = False
        r = self.api_post('/rest/p/test/wiki', access_token='foo')
        assert_equal(r.status_int, 403)
        OAuthAccessToken.query.get.assert_called_once_with(api_key='foo')

    @mock.patch('allura.controllers.rest.M.OAuthAccessToken')
    @mock.patch('allura.controllers.rest.request')
    def test_bearer_token_invalid(self, request, OAuthAccessToken):
        request.params = {'access_token': 'foo'}
        request.scheme = 'https'
        OAuthAccessToken.query.get.return_value = None
        r = self.api_post('/rest/p/test/wiki', access_token='foo')
        assert_equal(r.status_int, 403)

    @mock.patch('allura.controllers.rest.request')
    @td.with_wiki
    def test_bearer_token_valid(self, request):
        user = M.User.by_username('test-admin')
        consumer_token = M.OAuthConsumerToken(
            name='foo',
            description='foo app',
        )
        request_token = M.OAuthRequestToken(
            consumer_token_id=consumer_token._id,
            user_id=user._id,
            callback='manual',
            validation_pin=h.nonce(20),
            is_bearer=True,
        )
        access_token = M.OAuthAccessToken(
            consumer_token_id=consumer_token._id,
            request_token_id=request_token._id,
            user_id=user._id,
            is_bearer=True,
        )
        ThreadLocalODMSession.flush_all()
        request.params = {'access_token': access_token.api_key}
        request.scheme = 'https'
        r = self.api_post('/rest/p/test/wiki', access_token='foo')
        assert_equal(r.status_int, 200)

    def test_bad_path(self):
        r = self.api_post('/rest/1/test/wiki/')
        assert r.status_int == 404
        r = self.api_post('/rest/p/1223/wiki/')
        assert r.status_int == 404
        r = self.api_post('/rest/p/test/12wiki/')
        assert r.status_int == 404

    def test_no_api(self):
        r = self.api_post('/rest/p/test/admin/')
        assert r.status_int == 404

    @td.with_wiki
    def test_project_ping(self):
        r = self.api_get('/rest/p/test/wiki/Home/')
        assert r.status_int == 200
        assert r.json['title'] == 'Home', r.json

    @td.with_tool('test/sub1', 'Wiki', 'wiki')
    def test_subproject_ping(self):
        r = self.api_get('/rest/p/test/sub1/wiki/Home/')
        assert r.status_int == 200
        assert r.json['title'] == 'Home', r.json

    def test_project_code(self):
        r = self.api_get('/rest/p/test/')
        assert r.status_int == 200

    def test_project_data(self):
        r = self.api_get('/rest/p/test/')
        assert_equal(r.json['shortname'], 'test')
        assert_equal(r.json['name'], 'Test Project')
        assert_equal(len(r.json['developers']), 1)
        admin_dev = r.json['developers'][0]
        assert_equal(admin_dev['username'], 'test-admin')
        assert_equal(admin_dev['name'], 'Test Admin')
        assert_equal(admin_dev['url'], 'http://localhost/u/test-admin/')

    @td.with_tool('test', 'Tickets', 'bugs')
    @td.with_tool('test', 'Tickets', 'private-bugs')
    def test_project_data_tools(self):
        # Deny anonymous to see 'private-bugs' tool
        role = M.ProjectRole.by_name('*anonymous')._id
        read_permission = M.ACE.allow(role, 'read')
        app = M.Project.query.get(
            shortname='test').app_instance('private-bugs')
        if read_permission in app.config.acl:
            app.config.acl.remove(read_permission)

        # admin sees both 'Tickets' tools
        r = self.api_get('/rest/p/test/')
        assert_equal(r.json['shortname'], 'test')
        tool_mounts = [t['mount_point'] for t in r.json['tools']]
        assert_in('bugs', tool_mounts)
        assert_in('private-bugs', tool_mounts)

        # anonymous sees only non-private tool
        r = self.app.get('/rest/p/test/',
                         extra_environ={'username': '*anonymous'})
        assert_equal(r.json['shortname'], 'test')
        tool_mounts = [t['mount_point'] for t in r.json['tools']]
        assert_in('bugs', tool_mounts)
        assert_not_in('private-bugs', tool_mounts)

    def test_unicode(self):
        self.app.post(
            '/wiki/tést/update',
            params={
                'title': 'tést',
                'text': 'sometext',
                'labels': '',
                'viewable_by-0.id': 'all'})
        r = self.api_get('/rest/p/test/wiki/tést/')
        assert r.status_int == 200
        assert r.json['title'].encode('utf-8') == 'tést', r.json

    @td.with_wiki
    def test_deny_access(self):
        wiki = M.Project.query.get(shortname='test').app_instance('wiki')
        anon_read_perm = M.ACE.allow(
            M.ProjectRole.by_name('*anonymous')._id, 'read')
        auth_read_perm = M.ACE.allow(
            M.ProjectRole.by_name('*authenticated')._id, 'read')
        acl = wiki.config.acl
        if anon_read_perm in acl:
            acl.remove(anon_read_perm)
        if auth_read_perm in acl:
            acl.remove(auth_read_perm)
        self.app.get('/rest/p/test/wiki/Home/',
                     extra_environ={'username': '*anonymous'},
                     status=401)
        self.app.get('/rest/p/test/wiki/Home/',
                     extra_environ={'username': 'test-user-0'},
                     status=403)

    def test_index(self):
        eps = {
            'site_stats': {
                'foo_24hr': lambda: 42,
                'bar_24hr': lambda: 84,
                'qux_24hr': lambda: 0,
            },
        }
        with mock.patch.dict(g.entry_points, eps):
            response = self.app.get('/rest/')
            assert_equal(response.json, {
                'site_stats': {
                    'foo_24hr': 42,
                    'bar_24hr': 84,
                    'qux_24hr': 0,
                },
            })

    def test_name_validation(self):
        r = self.api_get('/rest/p/test/')
        assert r.status_int == 200
        with mock.patch('allura.lib.plugin.ProjectRegistrationProvider') as Provider:
            Provider.get().shortname_validator.to_python.side_effect = Invalid(
                'name', 'value', {})
            r = self.api_get('/rest/p/test/')
            assert r.status_int == 404

class TestDoap(TestRestApiBase):
    validate_skip = True
    ns = '{http://usefulinc.com/ns/doap#}'
    ns_sf = '{http://sourceforge.net/api/sfelements.rdf#}'
    foaf = '{http://xmlns.com/foaf/0.1/}'

    def test_project_data(self):
        r = self.app.get('/rest/p/test?doap')
        assert_equal(r.content_type, 'application/rdf+xml')
        p = r.xml.find(self.ns + 'Project')
        assert_equal(p.find(self.ns + 'name').text, 'Test Project')
        assert_equal(p.find(self.ns_sf + 'shortname').text, 'test')
        assert p.find(self.ns_sf + 'id') is not None

        maintainers = p.findall(self.ns + 'maintainer')
        assert_equal(len(maintainers), 1)
        user = maintainers[0].find(self.foaf + 'Person')
        assert_equal(user.find(self.foaf + 'name').text, 'Test Admin')
        assert_equal(user.find(self.foaf + 'nick').text, 'test-admin')
        assert_equal(user.find(self.foaf + 'homepage').items()[0][1],
                     'http://localhost/u/test-admin/')

    @td.with_tool('test', 'Tickets', 'bugs')
    @td.with_tool('test', 'Tickets', 'private-bugs')
    def test_project_data_tools(self):
        # Deny anonymous to see 'private-bugs' tool
        role = M.ProjectRole.by_name('*anonymous')._id
        read_permission = M.ACE.allow(role, 'read')
        app = M.Project.query.get(
            shortname='test').app_instance('private-bugs')
        if read_permission in app.config.acl:
            app.config.acl.remove(read_permission)

        # admin sees both 'Tickets' tools
        r = self.app.get('/rest/p/test?doap')
        p = r.xml.find(self.ns + 'Project')
        tools = p.findall(self.ns_sf + 'feature')
        tools = [(t.find(self.ns_sf + 'Feature').find(self.ns + 'name').text,
                  t.find(self.ns_sf + 'Feature').find(self.foaf + 'page').items()[0][1])
                 for t in tools]
        assert_in(('Tickets', 'http://localhost/p/test/bugs/'), tools)
        assert_in(('Tickets', 'http://localhost/p/test/private-bugs/'), tools)

        # anonymous sees only non-private tool
        r = self.app.get('/rest/p/test?doap',
                         extra_environ={'username': '*anonymous'})
        p = r.xml.find(self.ns + 'Project')
        tools = p.findall(self.ns_sf + 'feature')
        tools = [(t.find(self.ns_sf + 'Feature').find(self.ns + 'name').text,
                  t.find(self.ns_sf + 'Feature').find(self.foaf + 'page').items()[0][1])
                 for t in tools]
        assert_in(('Tickets', 'http://localhost/p/test/bugs/'), tools)
        assert_not_in(('Tickets', 'http://localhost/p/test/private-bugs/'), tools)

    @td.with_tool('test', 'Tickets', 'bugs')
    def test_tools_additional_entries(self):
        with mock.patch.object(ForgeTrackerApp, 'additional_doap_entries') as add:
            add.return_value = [Node('additional-entry1', 'some text1'),
                                Node('additional-entry2', 'some text2'),]
            r = self.app.get('/rest/p/test?doap')
        p = r.xml.find(self.ns + 'Project')
        assert_equal(p.find(self.ns + 'additional-entry1').text, 'some text1')
        assert_equal(p.find(self.ns + 'additional-entry2').text, 'some text2')
