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
from datetime import datetime
from nose.tools import assert_equal, assert_true
from tg import tmpl_context as c

from forgefeedback.tests.unit import FeedbackTestWithModel
from forgefeedback import model as M


class TestFeedback(FeedbackTestWithModel):

    def test_feedback(self):
        feedback = M.Feedback()
        feedback.rating = '4'
        feedback.description = 'Very good tool'
        assert_equal(feedback.rating, '4')
        assert_equal(feedback.description, 'Very good tool')
        assert_equal(feedback.activity_extras['summary'], feedback.description)
        assert_true('allura_id' in feedback.activity_extras)

    def test_index(self):
        feedback = M.Feedback()
        feedback.rating = '4'
        feedback.description = 'Good tool'
        result = feedback.index()
        assert_equal(result["text"], 'Good tool')
