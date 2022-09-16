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
from tg import tmpl_context as c
from tg import config

from allura import model as M
from alluratest.controller import TestController
from allura.lib import helpers as h
from allura.tests import decorators as td

from forgefeedback import model as FM


class TestFeedback(TestController):

    def test_feedback(self):
        c.user = M.User.by_username('test-admin')
        self.app.get('/feedback/')
        r = self.app.get('/p/test/feedback')
        assert 'test' in r
        assert '<a href="/p/test/feedback/new_feedback">Feedback</a>' in r

    def test_new_feedback(self):
        c.user = M.User.by_username('test-admin')
        self.app.get('/feedback/')
        r = self.app.get('/p/test/feedback/new_feedback/')
        assert 'Provide your feedback for <b> Test Project</b>' in r
        assert 'Enter your feedback here' in r

    def test_create_feedback(self):
        resp = post_feedback(self)
        resp = resp.follow()
        assert 'Good tool' in resp

    def test_edit_feedback(self):
        post_feedback(self)
        data = {'rating': '2', 'description': 'Not useful'}
        resp = self.app.post('/p/test/feedback/edit_user_review', data)
        resp = resp.follow()
        assert 'Not useful' in resp

    def test_delete_feedback(self):
        post_feedback(self)
        resp = self.app.post('/p/test/feedback/delete_feedback')
        assert 'Success' in resp


def post_feedback(self):
    c.user = M.User.by_username('test-admin')
    self.app.get('/feedback/')
    self.app.get('/p/test/feedback')
    data = {'rating': '4', 'description': 'Good tool'}
    resp = self.app.post('/p/test/feedback/create_feedback/', data)
    return resp
