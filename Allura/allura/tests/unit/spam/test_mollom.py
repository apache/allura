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


import mock
import unittest
import urllib


from allura.lib.spam.mollomfilter import MOLLOM_AVAILABLE, MollomSpamFilter


@unittest.skipIf(not MOLLOM_AVAILABLE, "Mollom not available")
class TestMollom(unittest.TestCase):

    @mock.patch('allura.lib.spam.mollomfilter.Mollom')
    def setUp(self, mollom_lib):
        self.mollom = MollomSpamFilter({})

        def side_effect(*args, **kw):
            # side effect to test that data being sent to
            # mollom can be successfully urlencoded
            urllib.urlencode(kw.get('data', {}))
            return dict(spam=2)
        self.mollom.service.checkContent = mock.Mock(side_effect=side_effect,
                                                     return_value=dict(spam=2))
        self.fake_artifact = mock.Mock(**{'url.return_value': 'artifact url'})
        self.fake_user = mock.Mock(display_name=u'Søme User',
                                   email_addresses=['user@domain'])
        self.fake_headers = dict(
            USER_AGENT='some browser',
            REFERER='some url')
        self.content = u'spåm text'
        self.expected_data = dict(
            postBody=self.content.encode('utf8'),
            authorIP='some ip')
        self.artifact = mock.Mock()
        self.artifact.spam_check_id = 'test_id'

    @mock.patch('allura.lib.spam.mollomfilter.c')
    @mock.patch('allura.lib.spam.mollomfilter.request')
    def test_check(self, request, c):
        request.headers = self.fake_headers
        request.remote_addr = 'some ip'
        c.user = None
        self.mollom.check(self.content, artifact=self.artifact)
        self.mollom.service.checkContent.assert_called_once_with(
            **self.expected_data)

    @mock.patch('allura.lib.spam.mollomfilter.c')
    @mock.patch('allura.lib.spam.mollomfilter.request')
    def test_check_with_user(self, request, c):
        request.headers = self.fake_headers
        request.remote_addr = 'some ip'
        c.user = None
        self.mollom.check(self.content, user=self.fake_user,
                          artifact=self.artifact)
        expected_data = self.expected_data
        expected_data.update(authorName=u'Søme User'.encode('utf8'),
                             authorMail='user@domain')
        self.mollom.service.checkContent.assert_called_once_with(
            **self.expected_data)

    @mock.patch('allura.lib.spam.mollomfilter.c')
    @mock.patch('allura.lib.spam.mollomfilter.request')
    def test_check_with_implicit_user(self, request, c):
        request.headers = self.fake_headers
        request.remote_addr = 'some ip'
        c.user = self.fake_user
        self.mollom.check(self.content, artifact=self.artifact)
        expected_data = self.expected_data
        expected_data.update(authorName=u'Søme User'.encode('utf8'),
                             authorMail='user@domain')
        self.mollom.service.checkContent.assert_called_once_with(
            **self.expected_data)

    def test_submit_spam(self):
        self.mollom.submit_spam('test', artifact=self.artifact)
        assert self.mollom.service.sendFeedback.call_args[0] == (
            'test_id', 'spam'), self.mollom.service.sendFeedback.call_args[0]
