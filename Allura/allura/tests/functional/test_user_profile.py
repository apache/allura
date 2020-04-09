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
import mock
import tg
from nose.tools import assert_equal, assert_in, assert_not_in

from alluratest.controller import TestRestApiBase
from allura.model import Project, User
from allura.tests import decorators as td
from allura.tests import TestController
from six.moves import map


class TestUserProfile(TestController):

    @td.with_user_project('test-admin')
    def test_profile(self):
        r = self.app.get('/u/test-admin/profile/')
        assert_equal('Test Admin',
                     r.html.find('h1', 'project_title').find('a').text)
        sections = set([c for s in r.html.findAll(None, 'profile-section') for c in s['class']])
        assert_in('personal-data', sections)
        assert_in('Username:\ntest-admin', r.html.find(None, 'personal-data').getText().replace(' ', ''))
        assert_in('projects', sections)
        assert_in('Test Project', r.html.find(None, 'projects').getText())
        assert_in('Last Updated:', r.html.find(None, 'projects').getText())
        assert_in('tools', sections)
        assert_in('Admin', r.html.find(None, 'tools').getText())
        assert_in('skills', sections)
        assert_in('No skills entered', r.html.find(None, 'skills').getText())

    @td.with_user_project('test-admin')
    def test_profile_user_card(self):
        user = User.by_username('test-admin')
        locals =  {
            'city': 'test-city',
            'country': 'US'
        }
        webpages = ['http://allura.apache.org/']
        user.set_pref('localization', locals)
        user.set_pref('webpages', webpages)
        r = self.app.get('/u/test-admin/profile/user_card')

        assert user.icon_url() in r.html.find('img').attrs['src']
        assert user.display_name == r.html.find('div', attrs={'class': 'name'}).getText()
        assert user.get_pref('localization')['city'] in r.html.find('span', attrs={'class': 'subitem-loc'}).getText()
        assert user.get_pref('localization')['country'] in r.html.find('span', attrs={'class': 'subitem-loc'}).getText()
        assert user.get_pref('webpages')[0] in str(r.html.find('span', attrs={'class': 'subitem-web'}))

    def test_wrong_profile(self):
        self.app.get('/u/no-such-user/profile/', status=404)

    @td.with_user_project('test-user')
    def test_missing_user(self):
        User.query.remove(dict(username='test-user'))
        p = Project.query.get(shortname='u/test-user')
        assert p is not None and p.is_user_project
        response = self.app.get('/u/test-user/profile/', status=404)

    def test_differing_profile_proj_shortname(self):
        User.upsert('foo_bar')
        # default auth provider's user_project_shortname() converts _ to - (for subdomain name validation reasons)
        # but can access user URL with "_" still
        self.app.get('/u/foo_bar/profile/')

        # and accessing it by "-" which was the previous way, will redirect
        response = self.app.get('/u/foo-bar/', status=302)
        assert_equal(response.location, 'http://localhost/u/foo_bar/')
        response = self.app.get('/u/foo-bar/profile/xyz?a=b', status=302)
        assert_equal(response.location, 'http://localhost/u/foo_bar/profile/xyz?a=b')

    def test_differing_profile_proj_shortname_rest_api(self):
        User.upsert('foo_bar')
        # default auth provider's user_project_shortname() converts _ to - (for subdomain name validation reasons)
        # but can access user URL with "_" still
        self.app.get('/rest/u/foo_bar/')
        # and with "-" too, no redirect here to avoid api clients having to deal with unexpected redirects
        self.app.get('/rest/u/foo-bar/')

    @td.with_user_project('test-admin')
    @td.with_wiki
    def test_feed(self):
        for ext in ['', '.rss', '.atom']:
            r = self.app.get('/u/test-admin/profile/feed%s' % ext, status=200)
            assert 'Recent posts by Test Admin' in r
            assert 'Home modified by Test Admin' in r

    @td.with_user_project('test-admin')
    @td.with_user_project('test-user')
    @mock.patch('allura.tasks.mail_tasks.sendsimplemail')
    @mock.patch('allura.lib.helpers.gen_message_id')
    @mock.patch('allura.model.User.can_send_user_message')
    def test_send_message(self, check, gen_message_id, sendsimplemail):
        check.return_value = True
        gen_message_id.return_value = 'id'
        test_user = User.by_username('test-user')
        test_user.set_pref('email_address', 'test-user@example.com')
        response = self.app.get(
            '/u/test-user/profile/send_message', status=200)
        assert 'you currently have user messages disabled' not in response
        assert '<b>From:</b> &#34;Test Admin&#34; &lt;test-admin@users.localhost&gt;' in response

        self.app.post('/u/test-user/profile/send_user_message',
                      params={'subject': 'test subject',
                              'message': 'test message',
                              'cc': 'on'})

        sendsimplemail.post.assert_called_once_with(
            cc=User.by_username('test-admin').get_pref('email_address'),
            text='test message\n\n---\n\nThis message was sent to you via the Allura web mail form.  You may reply to this message directly, or send a message to Test Admin at http://localhost/u/test-admin/profile/send_message\n',
            toaddr=User.by_username('test-user').get_pref('email_address'),
            fromaddr=User.by_username('test-admin').get_pref('email_address'),
            reply_to=User.by_username('test-admin').get_pref('email_address'),
            message_id='id',
            subject='test subject')
        sendsimplemail.reset_mock()
        self.app.post('/u/test-user/profile/send_user_message',
                      params={'subject': 'test subject',
                              'message': 'test message'})

        sendsimplemail.post.assert_called_once_with(
            cc=None,
            text='test message\n\n---\n\nThis message was sent to you via the Allura web mail form.  You may reply to this message directly, or send a message to Test Admin at http://localhost/u/test-admin/profile/send_message\n',
            toaddr=User.by_username('test-user').get_pref('email_address'),
            fromaddr=User.by_username('test-admin').get_pref('email_address'),
            reply_to=User.by_username('test-admin').get_pref('email_address'),
            message_id='id',
            subject='test subject')

        check.return_value = False
        response = self.app.get(
            '/u/test-user/profile/send_message', status=200)
        assert 'Sorry, messaging is rate-limited' in response

    @td.with_user_project('test-user')
    def test_send_message_for_anonymous(self):
        r = self.app.get('/u/test-user/profile/send_message',
                         extra_environ={'username': str('*anonymous')},
                         status=302)
        assert 'You must be logged in to send user messages.' in self.webflash(
            r)

        r = self.app.post('/u/test-user/profile/send_user_message',
                          params={'subject': 'test subject',
                                  'message': 'test message',
                                  'cc': 'on'},
                          extra_environ={'username': str('*anonymous')},
                          status=302)
        assert 'You must be logged in to send user messages.' in self.webflash(
            r)

    @td.with_user_project('test-user')
    def test_link_to_send_message_form(self):
        User.by_username('test-admin').set_pref('email_address',
                                                'admin@example.com')
        User.by_username('test-user').set_pref('email_address',
                                               'user@example.com')
        r = self.app.get('/u/test-user/profile',
                         status=200)
        assert r.html.find('a', dict(href='/u/test-user/profile/send_message'))

    @td.with_user_project('test-user')
    def test_disable_user_messages(self):
        User.by_username('test-admin').set_pref('email_address',
                                                'admin@example.com')
        test_user = User.by_username('test-user')
        test_user.set_pref('email_address', 'user@example.com')
        test_user.set_pref('disable_user_messages', True)
        r = self.app.get('/u/test-user/profile')
        assert '<a href="send_message">Send me a message</a>' not in r
        r = self.app.get('/u/test-user/profile/send_message', status=302)
        assert 'This user has disabled direct email messages' in self.webflash(
            r)

    @td.with_user_project('test-admin')
    @td.with_user_project('test-user')
    def test_user_messages_sender_disabled(self):
        admin_user = User.by_username('test-admin')
        admin_user.set_pref('email_address', 'admin@example.com')
        admin_user.set_pref('disable_user_messages', True)

        test_user = User.by_username('test-user')
        test_user.set_pref('email_address', 'user@example.com')

        r = self.app.get('/u/test-user/profile/send_message', status=200)
        assert 'you currently have user messages disabled' in r

    @td.with_user_project('test-user')
    def test_profile_sections(self):
        project = Project.query.get(shortname='u/test-user')
        app = project.app_instance('profile')

        def ep(n):
            m = mock.Mock()
            m.name = n
            m.load()().display.return_value = 'Section %s' % n
            return m
        eps = list(map(ep, ['a', 'b', 'c', 'd']))
        order = {'user_profile_sections.order': 'b, d,c , f '}
        if hasattr(type(app), '_sections'):
            delattr(type(app), '_sections')
        with mock.patch('allura.lib.helpers.iter_entry_points') as iep:
            with mock.patch.dict(tg.config, order):
                iep.return_value = eps
                sections = app.profile_sections
                assert_equal(sections, [
                    eps[1].load(),
                    eps[3].load(),
                    eps[2].load(),
                    eps[0].load()])
        r = self.app.get('/u/test-user/profile')
        assert_in('Section a', r.text)
        assert_in('Section b', r.text)
        assert_in('Section c', r.text)
        assert_in('Section d', r.text)
        assert_not_in('Section f', r.text)


class TestUserProfileHasAccessAPI(TestRestApiBase):

    @td.with_user_project('test-admin')
    def test_has_access_no_params(self):
        self.api_get('/rest/u/test-admin/profile/has_access', status=404)
        self.api_get('/rest/u/test-admin/profile/has_access?user=root', status=404)
        self.api_get('/rest/u/test-admin/profile/has_access?perm=read', status=404)

    @td.with_user_project('test-admin')
    def test_has_access_unknown_params(self):
        """Unknown user and/or permission always False for has_access API"""
        r = self.api_get(
            '/rest/u/test-admin/profile/has_access?user=babadook&perm=read',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
        r = self.api_get(
            '/rest/u/test-admin/profile/has_access?user=test-user&perm=jump',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)

    @td.with_user_project('test-admin')
    def test_has_access_not_admin(self):
        """
        User which has no 'admin' permission on neighborhood can't use
        has_access API
        """
        self.api_get(
            '/rest/u/test-admin/profile/has_access?user=test-admin&perm=admin',
            user='test-user',
            status=403)

    @td.with_user_project('test-admin')
    def test_has_access(self):
        r = self.api_get(
            '/rest/u/test-admin/profile/has_access?user=test-admin&perm=admin',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], True)
        r = self.api_get(
            '/rest/u/test-admin/profile/has_access?user=test-user&perm=admin',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
