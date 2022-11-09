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

import mock
import tg

from alluratest.controller import TestRestApiBase
from allura.model import Project, User
from allura.tests import decorators as td
from allura.tests import TestController


class TestUserProfileSections(TestController):

    def teardown_method(self, method):
        super().teardown_method(method)
        project = Project.query.get(shortname='u/test-user')
        app = project.app_instance('profile')
        if hasattr(type(app), '_sections'):
            delattr(type(app), '_sections')

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
                assert sections == [
                    eps[1].load(),
                    eps[3].load(),
                    eps[2].load(),
                    eps[0].load()]
        r = self.app.get('/u/test-user/profile')
        assert 'Section a' in r.text
        assert 'Section b' in r.text
        assert 'Section c' in r.text
        assert 'Section d' in r.text
        assert 'Section f' not in r.text


class TestUserProfile(TestController):

    @td.with_user_project('test-admin')
    def test_profile(self):
        r = self.app.get('/u/test-admin/profile/')
        assert ('Test Admin' ==
                     r.html.find('h1', 'project_title').find('a').text)
        sections = {c for s in r.html.findAll(None, 'profile-section') for c in s['class']}
        assert 'personal-data' in sections
        assert 'Username:\ntest-admin' in r.html.find(None, 'personal-data').getText().replace(' ', '')
        assert 'projects' in sections
        assert 'Test Project' in r.html.find(None, 'projects').getText()
        assert 'Last Updated:' in r.html.find(None, 'projects').getText()
        assert 'tools' in sections
        assert 'Admin' in r.html.find(None, 'tools').getText()
        assert 'skills' in sections
        assert 'No skills entered' in r.html.find(None, 'skills').getText()

    @td.with_user_project('test-admin')
    @mock.patch.dict(tg.config, {'use_gravatar': 'true'})
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
        assert response.location == 'http://localhost/u/foo_bar/'
        response = self.app.get('/u/foo-bar/profile/xyz?a=b', status=302)
        assert response.location == 'http://localhost/u/foo_bar/profile/xyz?a=b'

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
        response.mustcontain('<b>From:</b> Test Admin')

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

    @td.with_user_project('test-admin')
    @td.with_user_project('test-user')
    @mock.patch('allura.tasks.mail_tasks.sendsimplemail')
    @mock.patch('allura.lib.helpers.gen_message_id')
    @mock.patch('allura.model.User.can_send_user_message')
    def test_send_message_with_real_address_reply(self, check, gen_message_id, sendsimplemail):
        check.return_value = True
        gen_message_id.return_value = 'id'
        test_user = User.by_username('test-user')
        test_admin = User.by_username('test-admin')
        test_user.set_pref('email_address', 'test-user@example.com')
        response = self.app.get(
            '/u/test-user/profile/send_message', status=200)
        assert 'you currently have user messages disabled' not in response
        response.mustcontain('<b>From:</b> Test Admin')
        self.app.post('/u/test-user/profile/send_user_message',
                      params={'subject': 'test subject',
                              'message': 'test message',
                              'cc': 'on',
                              'reply_to_real_address': 'on'})
        sender_address = test_admin.preferences.email_address
        sendsimplemail.post.assert_called_once_with(
            cc=User.by_username('test-admin').get_pref('email_address'),
            text='test message\n\n---\n\nThis message was sent to you via the Allura web mail form.  You may reply to this message directly, or send a message to Test Admin at http://localhost/u/test-admin/profile/send_message\n',
            toaddr=User.by_username('test-user').get_pref('email_address'),
            fromaddr=User.by_username('test-admin').get_pref('email_address'),
            reply_to=sender_address,
            message_id='id',
            subject='test subject')

    @td.with_user_project('test-user')
    def test_send_message_for_anonymous(self):
        r = self.app.get('/u/test-user/profile/send_message',
                         extra_environ={'username': '*anonymous'},
                         status=302)
        assert 'You must be logged in to send user messages.' in self.webflash(r)

        r = self.app.post('/u/test-user/profile/send_user_message',
                          params={'subject': 'test subject',
                                  'message': 'test message',
                                  'cc': 'on'},
                          extra_environ={'username': '*anonymous'},
                          status=302)
        assert 'You must be logged in to send user messages.' in self.webflash(r)

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

    def test_no_index_tag_in_empty_profile(self):
        r = self.app.get('/u/test-user/profile/')
        assert 'content="noindex, follow"' in r.text

    def test_remove_no_index_tag_profile(self):
        r = self.app.get('/u/test-admin/profile/')
        assert 'content="noindex, follow"' not in r.text


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
        assert r.status_int == 200
        assert r.json['result'] is False
        r = self.api_get(
            '/rest/u/test-admin/profile/has_access?user=test-user&perm=jump',
            user='root')
        assert r.status_int == 200
        assert r.json['result'] is False

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
        assert r.status_int == 200
        assert r.json['result'] is True
        r = self.api_get(
            '/rest/u/test-admin/profile/has_access?user=test-user&perm=admin',
            user='root')
        assert r.status_int == 200
        assert r.json['result'] is False
