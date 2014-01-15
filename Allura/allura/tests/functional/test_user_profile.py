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
from nose.tools import assert_equal, assert_in, assert_not_in

from allura.model import Project, User
from allura.tests import decorators as td
from allura.tests import TestController


class TestUserProfile(TestController):

    @td.with_user_project('test-admin')
    def test_profile(self):
        response = self.app.get('/u/test-admin/profile/')
        assert '<h2 class="dark title">Test Admin' in response
        assert 'OpenIDs' in response

    def test_wrong_profile(self):
        self.app.get('/u/no-such-user/profile/', status=404)

    @td.with_user_project('test-admin')
    @td.with_user_project('test-user')
    def test_seclusion(self):
        response = self.app.get('/u/test-admin/profile/')
        assert 'Email Addresses' in response
        self.app.get('/u/test-user', extra_environ=dict(
            username='test-user'))
        response = self.app.get('/u/test-user/profile/')
        assert 'Email Addresses' not in response

    @td.with_user_project('test-user')
    def test_missing_user(self):
        User.query.remove(dict(username='test-user'))
        p = Project.query.get(shortname='u/test-user')
        assert p is not None and p.is_user_project
        response = self.app.get('/u/test-user/profile/', status=404)
        assert 'Email Addresses' not in response

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
        assert '<b>From:</b> &#34;Test Admin&#34; &lt;test-admin@users.localhost&gt;' in response
        self.app.post('/u/test-user/profile/send_user_message',
                      params={'subject': 'test subject',
                              'message': 'test message',
                              'cc': 'on'})

        sendsimplemail.post.assert_called_once_with(
            cc=User.by_username('test-admin').get_pref('email_address'),
            text=u'test message\n\n---\n\nThis message was sent to you via the Allura web mail form.  You may reply to this message directly, or at http://localhost/u/test-admin/profile/send_message\n',
            toaddr=User.by_username('test-user').get_pref('email_address'),
            fromaddr=User.by_username('test-admin').get_pref('email_address'),
            reply_to=User.by_username('test-admin').get_pref('email_address'),
            message_id=u'id',
            subject=u'test subject')
        sendsimplemail.reset_mock()
        self.app.post('/u/test-user/profile/send_user_message',
                      params={'subject': 'test subject',
                              'message': 'test message'})

        sendsimplemail.post.assert_called_once_with(
            cc=None,
            text=u'test message\n\n---\n\nThis message was sent to you via the Allura web mail form.  You may reply to this message directly, or at http://localhost/u/test-admin/profile/send_message\n',
            toaddr=User.by_username('test-user').get_pref('email_address'),
            fromaddr=User.by_username('test-admin').get_pref('email_address'),
            reply_to=User.by_username('test-admin').get_pref('email_address'),
            message_id=u'id',
            subject=u'test subject')

        check.return_value = False
        response = self.app.get(
            '/u/test-user/profile/send_message', status=200)
        assert 'Sorry, messaging is rate-limited' in response

    @td.with_user_project('test-user')
    def test_send_message_for_anonymous(self):
        r = self.app.get('/u/test-user/profile/send_message',
                         extra_environ={'username': '*anonymous'},
                         status=302)
        assert 'You must be logged in to send user messages.' in self.webflash(
            r)

        r = self.app.post('/u/test-user/profile/send_user_message',
                          params={'subject': 'test subject',
                                  'message': 'test message',
                                  'cc': 'on'},
                          extra_environ={'username': '*anonymous'},
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
        assert '<a href="send_message">Send me a message</a>' in r

        r = self.app.get('/u/test-user/profile',
                         extra_environ={'username': '*anonymous'},
                         status=200)

        assert '<a href="send_message">Send me a message</a>' not in r

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

    @td.with_user_project('test-user')
    def test_profile_sections(self):
        project = Project.query.get(shortname='u/test-user')
        app = project.app_instance('profile')
        def ep(n):
            m = mock.Mock()
            m.name = n
            m.load()().display.return_value = 'Section %s' % n
            return m
        eps = map(ep, ['a', 'b', 'c', 'd'])
        order = {'user_profile_sections.order': 'b, d,c , f '}
        with mock.patch('allura.lib.helpers.iter_entry_points') as iep:
            with mock.patch.dict(tg.config, order):
                iep.return_value = eps
                sections = app.profile_sections
                assert_equal(sections, [
                        eps[1].load(),
                        eps[3].load(),
                        eps[2].load(),
                        eps[0].load(),
                    ])
                r = self.app.get('/u/test-user/profile')
                assert_in('Section a', r.body)
                assert_in('Section b', r.body)
                assert_in('Section c', r.body)
                assert_in('Section d', r.body)
                assert_not_in('Section f', r.body)
