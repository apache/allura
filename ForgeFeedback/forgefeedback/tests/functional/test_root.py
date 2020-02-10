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
from tg import tmpl_context as c
from tg import config

from nose.tools import assert_equal, assert_in, assert_not_in
from nose.tools import assert_true, assert_false, assert_raises

from allura import model as M
from alluratest.controller import TestController
from allura.lib import helpers as h
from allura.tests import decorators as td

from forgefeedback import model as FM


class TestFeedback(TestController):

    def setUp(self):
        TestController.setUp(self)

    def test_feedback(self):
        c.user = M.User.by_username('test-admin')
        self.app.get('/feedback/')
        r = self.app.get('/p/test/feedback')
        assert 'test' in r
        assert_in('<a href="/p/test/feedback/new_feedback">Feedback</a>', r)

    def test_new_feedback(self):
        c.user = M.User.by_username('test-admin')
        self.app.get('/feedback/')
        r = self.app.get('/p/test/feedback/new_feedback/')
        assert_in('Provide your feedback for <b> Test Project</b>', r)
        assert_in('Enter your feedback here', r)

    def test_create_feedback(self):
        resp = post_feedback(self)
        assert_in('Good tool', resp)

    def test_edit_feedback(self):
        post_feedback(self)
        data = {'rating': '2', 'description': 'Not useful'}
        resp = self.app.post('/p/test/feedback/edit_user_review', data)
        assert_in('Not useful', resp)

    def test_delete_feedback(self):
        post_feedback(self)
        resp = self.app.post('/p/test/feedback/delete_feedback')
        assert_in('Success', resp)


def post_feedback(self):
    c.user = M.User.by_username('test-admin')
    self.app.get('/feedback/')
    self.app.get('/p/test/feedback')
    data = {'rating': '4', 'description': 'Good tool'}
    resp = self.app.post('/p/test/feedback/create_feedback/', data)
    return resp
