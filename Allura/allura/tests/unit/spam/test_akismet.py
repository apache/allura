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
import unittest
import six.moves.urllib.request
import six.moves.urllib.parse
import six.moves.urllib.error
from datetime import datetime

from bson import ObjectId

from allura.lib.spam.akismetfilter import AKISMET_AVAILABLE, AkismetSpamFilter


@unittest.skipIf(not AKISMET_AVAILABLE, "Akismet not available")
class TestAkismet(unittest.TestCase):

    @mock.patch('allura.lib.spam.akismetfilter.akismet')
    def setup_method(self, method, akismet_lib):
        self.akismet = AkismetSpamFilter({'spam.key': 'example', 'base_url': 'http://localhost/'})

        def side_effect(*args, **kw):
            # side effect to test that data being sent to
            # akismet can be successfully urlencoded
            six.moves.urllib.parse.urlencode(kw.get('data', {}))
        self.akismet.service.comment_check = mock.Mock(side_effect=side_effect)
        self.akismet.service.submit_spam = mock.Mock(side_effect=side_effect)
        self.akismet.service.submit_ham = mock.Mock(side_effect=side_effect)
        self.fake_artifact = mock.Mock(**{
            'main_url.return_value': '/artifact-url',
            'project_id': ObjectId(),
            'ref': None,
            'timestamp': datetime(2019, 5, 17),
            'primary.return_value': mock.Mock(
                mod_date=datetime(2019, 5, 17, 0, 5, 1)
            ),
            'get_version.return_value': mock.Mock(
                author=mock.Mock(
                    logged_ip='33.4.5.66',
                )
            ),
        })
        self.fake_user = mock.Mock(display_name='Søme User',
                                   email_addresses=['user@domain'],
                                   _id=ObjectId())
        self.fake_headers = dict(
            USER_AGENT='some browser',
            REFERER='some url')
        self.content = 'spåm text'
        self.expected_data = dict(
            comment_content=self.content.encode('utf8'),
            comment_type=b'comment',
            user_ip=b'some ip',
            user_agent=b'some browser',
            referrer=b'some url')

    @mock.patch('allura.lib.spam.akismetfilter.c')
    @mock.patch('allura.lib.spam.akismetfilter.request')
    def test_check(self, request, c):
        request.headers = self.fake_headers
        request.remote_addr = 'some ip'
        c.user = None
        self.akismet.service.comment_check.side_effect({'side_effect': ''})
        self.akismet.check(self.content)
        self.akismet.service.comment_check.assert_called_once_with(**self.expected_data)

    @mock.patch('allura.lib.spam.akismetfilter.c')
    @mock.patch('allura.lib.spam.akismetfilter.request')
    def test_check_with_explicit_content_type(self, request, c):
        request.headers = self.fake_headers
        request.remote_addr = 'some ip'
        c.user = None
        self.akismet.check(self.content, content_type='some content type')
        self.expected_data['comment_type'] = b'some content type'
        self.akismet.service.comment_check.assert_called_once_with(**self.expected_data)

    @mock.patch('allura.lib.spam.akismetfilter.c')
    @mock.patch('allura.lib.spam.akismetfilter.request')
    def test_check_with_artifact(self, request, c):
        request.headers = self.fake_headers
        request.remote_addr = 'some ip'
        c.user = None
        self.akismet.check(self.content, artifact=self.fake_artifact)
        expected_data = self.expected_data
        expected_data['permalink'] = b'http://localhost/artifact-url'
        expected_data['comment_date_gmt'] = b'2019-05-17T00:00:00'
        expected_data['comment_post_modified_gmt'] = b'2019-05-17T00:05:01'
        self.akismet.service.comment_check.assert_called_once_with(**expected_data)

    @mock.patch('allura.lib.spam.akismetfilter.c')
    @mock.patch('allura.lib.spam.akismetfilter.request')
    def test_check_with_user(self, request, c):
        request.headers = self.fake_headers
        request.remote_addr = 'some ip'
        c.user = None
        self.akismet.check(self.content, user=self.fake_user)
        expected_data = self.expected_data
        expected_data.update(comment_author='Søme User'.encode(),
                             comment_author_email=b'user@domain')
        self.akismet.service.comment_check.assert_called_once_with(**expected_data)

    @mock.patch('allura.lib.spam.akismetfilter.c')
    @mock.patch('allura.lib.spam.akismetfilter.request')
    def test_check_with_implicit_user(self, request, c):
        request.headers = self.fake_headers
        request.remote_addr = 'some ip'
        c.user = self.fake_user
        self.akismet.check(self.content)
        expected_data = self.expected_data
        expected_data.update(comment_author='Søme User'.encode(),
                             comment_author_email=b'user@domain')
        self.akismet.service.comment_check.assert_called_once_with(**expected_data)

    @mock.patch('allura.lib.spam.akismetfilter.c')
    def test_submit_spam(self, c):
        c.user = None

        self.akismet.submit_spam(self.content)

        # no IP addr, UA, etc, since this isn't the original request
        expected_data = dict(comment_content='spåm text'.encode(),
                             comment_type=b'comment',
                             user_ip=b'',
                             user_agent=b'',
                             )
        self.akismet.service.submit_spam.assert_called_once_with(**expected_data)

    @mock.patch('allura.lib.spam.akismetfilter.c')
    def test_submit_ham(self, c):
        c.user = None

        self.akismet.submit_ham(self.content)

        # no IP addr, UA, etc, since this isn't the original request
        expected_data = dict(comment_content='spåm text'.encode(),
                             comment_type=b'comment',
                             user_ip=b'',
                             user_agent=b'',
                             )
        self.akismet.service.submit_ham.assert_called_once_with(**expected_data)

    @mock.patch('allura.lib.spam.akismetfilter.c')
    def test_submit_ham_with_artifact(self, c):
        c.user = None

        self.akismet.submit_ham(self.content, artifact=self.fake_artifact)

        expected_data = dict(comment_content='spåm text'.encode(),
                             comment_type=b'comment',
                             user_ip=b'33.4.5.66',
                             user_agent=b'',
                             permalink=b'http://localhost/artifact-url',
                             comment_date_gmt=b'2019-05-17T00:00:00',
                             comment_post_modified_gmt=b'2019-05-17T00:05:01',
                             )
        self.akismet.service.submit_ham.assert_called_once_with(**expected_data)
