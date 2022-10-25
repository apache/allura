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

from ming.orm.ormsession import session
from tg import tmpl_context as c

from allura.lib import helpers as h
from allura.model import User

from forgefeedback.tests.unit import FeedbackTestWithModel
from forgefeedback.model import Feedback
from forgefeedback import feedback_main


class TestFeedbackApp(FeedbackTestWithModel):

    def setup_method(self, method):
        super().setup_method(method)
        c.user = User(username='test-user')
        h.set_context('test', 'feedback', neighborhood='Projects')

    def test_index(self):
        reviews = feedback_main.RootController().index()
        assert True if not reviews['user_has_already_reviewed'] else False
        create_feedbacks()
        reviews = feedback_main.RootController().index()
        assert True if reviews['user_has_already_reviewed'] else False

    def test_feedback(self):
        create_feedbacks()
        reviews = feedback_main.RootController().get_review_list()
        assert reviews[0].description == 'Very good tool'
        assert reviews[1].description == 'Not Useful'
        assert reviews[0].rating == '5'
        assert reviews[1].rating == '2'

    def test_getRating(self):
        create_feedbacks()
        rating = feedback_main.RootController().getRating()
        assert rating == 3.5

    def test_edit_feedback(self):
        create_feedbacks()
        old_feedback = feedback_main.RootController().edit_feedback()
        assert old_feedback['description'] == 'Very good tool'

    def test_check_feedback(self):
        feed_check = feedback_main.RootController().feedback_check('good')
        assert feed_check == 'false'
        feed_check = feedback_main.RootController().feedback_check('shit')
        assert feed_check == 'true'


def create_feedbacks():
    feedback_1 = create_feedback('2', 'Not Useful')
    c.user = User(username='test-admin')
    h.set_context('test', 'feedback', neighborhood='Projects')
    feedback_2 = create_feedback('5', 'Very good tool')


def create_feedback(rating, description):
    feedback = Feedback(rating=rating, description=description)
    session(feedback).flush()
    return feedback
