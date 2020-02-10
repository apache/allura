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

from __future__ import unicode_literals
from __future__ import absolute_import
from tg import app_globals as g
import mock
from nose.tools import assert_equal, assert_in, assert_not_in
from ming.odm import ThreadLocalODMSession
from tg import config

from allura.tests import decorators as td
from alluratest.controller import TestRestApiBase
from allura.lib import helpers as h
from allura.lib.exceptions import Invalid
from allura import model as M


class TestRestHome(TestRestApiBase):

    def _patch_token(self, OAuthAccessToken):
        at = OAuthAccessToken.return_value
        at.__ming__ = mock.MagicMock()
        at.api_key = 'foo'

    @mock.patch('allura.controllers.rest.M.OAuthAccessToken')
    @mock.patch('allura.controllers.rest.request')
    def test_bearer_token_non_bearer(self, request, OAuthAccessToken):
        request.headers = {}
        request.params = {'access_token': 'foo'}
        request.scheme = 'https'
        self._patch_token(OAuthAccessToken)
        access_token = OAuthAccessToken.query.get.return_value
        access_token.is_bearer = False
        r = self.api_post('/rest/p/test/wiki', access_token='foo', status=401)
        OAuthAccessToken.query.get.assert_called_once_with(api_key='foo')

    @mock.patch('allura.controllers.rest.M.OAuthAccessToken')
    @mock.patch('allura.controllers.rest.request')
    def test_bearer_token_invalid(self, request, OAuthAccessToken):
        request.headers = {}
        request.params = {'access_token': 'foo'}
        request.scheme = 'https'
        self._patch_token(OAuthAccessToken)
        OAuthAccessToken.query.get.return_value = None
        r = self.api_post('/rest/p/test/wiki', access_token='foo', status=401)

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
        request.headers = {}
        request.params = {'access_token': access_token.api_key}
        request.scheme = 'https'
        r = self.api_post('/rest/p/test/wiki', access_token='foo')
        assert_equal(r.status_int, 200)

    @mock.patch('allura.controllers.rest.M.OAuthAccessToken')
    @mock.patch('allura.controllers.rest.request')
    def test_bearer_token_non_bearer_via_headers(self, request, OAuthAccessToken):
        request.headers = {
            'Authorization': 'Bearer foo'
        }
        request.scheme = 'https'
        self._patch_token(OAuthAccessToken)
        access_token = OAuthAccessToken.query.get.return_value
        access_token.is_bearer = False
        r = self.api_post('/rest/p/test/wiki', access_token='foo', status=401)
        OAuthAccessToken.query.get.assert_called_once_with(api_key='foo')

    @mock.patch('allura.controllers.rest.M.OAuthAccessToken')
    @mock.patch('allura.controllers.rest.request')
    def test_bearer_token_invalid_via_headers(self, request, OAuthAccessToken):
        request.headers = {
            'Authorization': 'Bearer foo'
        }
        request.scheme = 'https'
        self._patch_token(OAuthAccessToken)
        OAuthAccessToken.query.get.return_value = None
        r = self.api_post('/rest/p/test/wiki', access_token='foo', status=401)

    @mock.patch('allura.controllers.rest.request')
    @td.with_wiki
    @mock.patch.dict(config, debug=False)
    def test_bearer_token_valid_via_headers(self, request):
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
        token = access_token.api_key
        request.headers = {
            'Authorization': 'Bearer {}'.format(token)
        }
        request.scheme = 'https'
        r = self.api_post('/rest/p/test/wiki', access_token='foo', status=200)
        # reverse proxy situation
        request.scheme = 'http'
        request.environ['paste.testing'] = False
        request.environ['HTTP_X_FORWARDED_PROTOx'] = 'https'
        r = self.api_post('/rest/p/test/wiki', access_token='foo', status=200)

    def test_bad_path(self):
        r = self.api_post('/rest/1/test/wiki/', status=404)
        r = self.api_post('/rest/p/1223/wiki/', status=404)
        r = self.api_post('/rest/p/test/12wiki/', status=404)

    def test_no_api(self):
        r = self.api_post('/rest/p/test/admin/', status=404)

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
                         extra_environ={'username': str('*anonymous')})
        assert_equal(r.json['shortname'], 'test')
        tool_mounts = [t['mount_point'] for t in r.json['tools']]
        assert_in('bugs', tool_mounts)
        assert_not_in('private-bugs', tool_mounts)

    def test_neighborhood_has_access_no_params(self):
        r = self.api_get('/rest/p/has_access', status=404)
        r = self.api_get('/rest/p/has_access?user=test-admin', status=404)
        r = self.api_get('/rest/p/has_access?perm=read', status=404)

    def test_neighborhood_has_access_unknown_params(self):
        """Unknown user and/or permission always False for has_access API"""
        r = self.api_get(
            '/rest/p/has_access?user=babadook&perm=read',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
        r = self.api_get(
            '/rest/p/has_access?user=test-admin&perm=jump',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)

    def test_neighborhood_has_access_not_admin(self):
        """
        User which has no 'admin' permission on neighborhood can't use
        has_access API
        """
        self.api_get(
            '/rest/p/has_access?user=test-admin&perm=admin',
            user='test-user',
            status=403)

    def test_neighborhood_has_access(self):
        r = self.api_get(
            '/rest/p/has_access?user=root&perm=update',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], True)
        r = self.api_get(
            '/rest/p/has_access?user=test-user&perm=update',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)

    def test_neighborhood(self):
        self.api_get('/rest/p/', status=404)

    def test_neighborhood_tools(self):
        r = self.api_get('/rest/p/wiki/Home/')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['title'], 'Home')

        r = self.api_get('/rest/p/admin/installable_tools', status=403)

        r = self.api_get('/rest/p/admin/installable_tools', user='root')
        assert_equal(r.status_int, 200)
        assert [t for t in r.json['tools'] if t['tool_label'] == 'Wiki'], r.json

    def test_project_has_access_no_params(self):
        self.api_get('/rest/p/test/has_access', status=404)
        self.api_get('/rest/p/test/has_access?user=root', status=404)
        self.api_get('/rest/p/test/has_access?perm=read', status=404)

    def test_project_has_access_unknown_params(self):
        """Unknown user and/or permission always False for has_access API"""
        r = self.api_get(
            '/rest/p/test/has_access?user=babadook&perm=read',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
        r = self.api_get(
            '/rest/p/test/has_access?user=test-admin&perm=jump',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)

    def test_project_has_access_not_admin(self):
        """
        User which has no 'admin' permission on neighborhood can't use
        has_access API
        """
        self.api_get(
            '/rest/p/test/has_access?user=test-admin&perm=admin',
            user='test-user',
            status=403)

    def test_project_has_access(self):
        r = self.api_get(
            '/rest/p/test/has_access?user=test-admin&perm=update',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], True)
        r = self.api_get(
            '/rest/p/test/has_access?user=test-user&perm=update',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)

    def test_subproject_has_access(self):
        r = self.api_get(
            '/rest/p/test/sub1/has_access?user=test-admin&perm=update',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], True)

    def test_unicode(self):
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode('utf-8'),
                'text': 'sometext',
                'labels': '',
                })
        r = self.api_get(h.urlquote('/rest/p/test/wiki/tést/'))
        assert r.status_int == 200
        assert r.json['title'] == 'tést', r.json

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
                     extra_environ={'username': str('*anonymous')},
                     status=401)
        self.app.get('/rest/p/test/wiki/Home/',
                     extra_environ={'username': str('test-user-0')},
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
            r = self.api_get('/rest/p/test/', status=404)

    @td.with_wiki
    def test_cors_POST_req_blocked_by_csrf(self):
        # so test-admin isn't automatically logged in for all requests
        self.app.extra_environ = {'disable_auth_magic': str('True')}

        # regular login to get a session cookie set up
        r = self.app.get('/auth/')
        encoded = self.app.antispam_field_names(r.form)
        r.form[encoded['username']] = 'test-admin'
        r.form[encoded['password']] = 'foo'
        r.form.submit()

        # simulate CORS ajax request withCredentials (cookie headers)
        # make sure we don't allow the cookies to authorize the request (else could be a CSRF attack vector)
        assert self.app.cookies['allura']
        self.app.post('/rest/p/test/wiki/NewPage', headers={'Origin': str('http://bad.com/')},
                      status=401)

    @mock.patch('allura.lib.plugin.ThemeProvider._get_site_notification')
    def test_notification(self, _get_site_notification):
        user = M.User.by_username('test-admin')
        note = M.SiteNotification()
        cookie = '{}-1-False'.format(note._id)
        g.theme._get_site_notification = mock.Mock(return_value=(note, cookie))

        r = self.app.get('/rest/notification?url=test_url&cookie=test_cookie&tool_name=test_tool')
        g.theme._get_site_notification.assert_called_once_with(
            url='test_url',
            user=user,
            tool_name='test_tool',
            site_notification_cookie_value='test_cookie'
        )

        assert r.status_int == 200
        assert r.json['cookie'] == cookie
        assert r.json['notification'] == note.__json__()

        g.theme._get_site_notification = mock.Mock(return_value=None)
        r = self.app.get('/rest/notification')
        assert r.json == {}



class TestDoap(TestRestApiBase):
    validate_skip = True
    ns = '{http://usefulinc.com/ns/doap#}'
    ns_sf = '{http://sourceforge.net/api/sfelements.rdf#}'
    foaf = '{http://xmlns.com/foaf/0.1/}'
    dc = '{http://dublincore.org/documents/dcmi-namespace/}'
    rdf = '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}'

    def test_project_data(self):
        project = M.Project.query.get(shortname='test')
        project.summary = 'A Summary'
        project.short_description = 'A Short Description'
        ThreadLocalODMSession.flush_all()
        r = self.app.get('/rest/p/test?doap')
        assert_equal(r.content_type, 'application/rdf+xml')
        p = r.xml.find(self.ns + 'Project')
        assert_equal(p.attrib[self.rdf + 'about'], 'http://localhost/rest/p/test?doap#')
        assert_equal(p.find(self.ns + 'name').text, 'test')
        assert_equal(p.find(self.dc + 'title').text, 'Test Project')
        assert_equal(p.find(self.ns_sf + 'private').text, '0')
        assert_equal(p.find(self.ns + 'shortdesc').text, 'A Summary')
        assert_equal(p.find(self.ns + 'description').text, 'A Short Description')
        assert_equal(p.find(self.ns + 'created').text, project._id.generation_time.strftime('%Y-%m-%d'))

        maintainers = p.findall(self.ns + 'maintainer')
        assert_equal(len(maintainers), 1)
        user = maintainers[0].find(self.foaf + 'Person')
        assert_equal(user.find(self.foaf + 'name').text, 'Test Admin')
        assert_equal(user.find(self.foaf + 'nick').text, 'test-admin')
        assert_equal(list(user.find(self.foaf + 'homepage').items())[0][1],
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
                  list(t.find(self.ns_sf + 'Feature').find(self.foaf + 'page').items())[0][1])
                 for t in tools]
        assert_in(('Tickets', 'http://localhost/p/test/bugs/'), tools)
        assert_in(('Tickets', 'http://localhost/p/test/private-bugs/'), tools)

        # anonymous sees only non-private tool
        r = self.app.get('/rest/p/test?doap',
                         extra_environ={'username': str('*anonymous')})
        p = r.xml.find(self.ns + 'Project')
        tools = p.findall(self.ns_sf + 'feature')
        tools = [(t.find(self.ns_sf + 'Feature').find(self.ns + 'name').text,
                  list(t.find(self.ns_sf + 'Feature').find(self.foaf + 'page').items())[0][1])
                 for t in tools]
        assert_in(('Tickets', 'http://localhost/p/test/bugs/'), tools)
        assert_not_in(('Tickets', 'http://localhost/p/test/private-bugs/'), tools)


class TestUserProfile(TestRestApiBase):
    @td.with_user_project('test-admin')
    def test_profile_data(self):
        r = self.app.get('/rest/u/test-admin/profile/')
        assert_equal(r.content_type, 'application/json')
        json = r.json
        assert_equal(json['username'], 'test-admin')
        assert_equal(json['name'], 'Test Admin')
        assert_in('availability', json)
        assert_in('joined', json)
        assert_in('localization', json)
        assert_in('projects', json)
        assert_in('sex', json)
        assert_in('skills', json)
        assert_in('skypeaccount', json)
        assert_in('socialnetworks', json)
        assert_in('telnumbers', json)
        assert_in('webpages', json)
