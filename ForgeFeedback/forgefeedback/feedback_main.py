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

import logging
import pymongo

# Non-stdlib imports

from tg import expose, flash, url, config, request, redirect
from tg.decorators import with_trailing_slash, without_trailing_slash
from tg import tmpl_context as c, app_globals as g
from ming.odm import session
from ming.orm import session

# profanityfilter package
from profanityfilter import ProfanityFilter

# Pyforge-specific imports

from allura import model as M
from allura import version
from allura.app import (
    Application,
)
from allura.controllers import BaseController
from allura.controllers.feed import FeedController
from allura.lib.decorators import require_post
from allura.lib.security import (require_access, has_access)
from allura.model import project

# Local imports

from forgefeedback import model as TM
from forgefeedback import version
from forgefeedback.model import Feedback

log = logging.getLogger(__name__)


class ForgeFeedbackApp(Application):

    __version__ = version.__version__
    permissions = [
        'read', 'update', 'create',
        'post', 'admin', 'delete'
    ]

    permissions_desc = {
        'read': 'View ratings.',
        'update': 'Edit ratings.',
        'create': 'Create ratings.',
        'admin': 'Set permissions. Configure option.',
        'delete': 'Delete and undelete ratings. View deleted ratings.'
    }

    config_options = Application.config_options + [
    ]
    tool_label = 'Feedback'
    tool_description = """
        Feedbacks are given for the tools in the form of reviews and ratings,
        edit and delete the feedback"""
    default_mount_label = 'Feedback'
    default_mount_point = 'feedback'
    ordinal = 8
    max_instances = 1

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()

    def install(self, project):
        'Set up any default permissions and roles here'
        super().install(project)
        # Setup permissions
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_developer = M.ProjectRole.by_name('Developer')._id
        role_auth = M.ProjectRole.by_name('*authenticated')._id
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_auth, 'post'),
            M.ACE.allow(role_auth, 'unmoderated_post'),
            M.ACE.allow(role_auth, 'create'),
            M.ACE.allow(role_developer, 'update'),
            M.ACE.allow(role_developer, 'moderate'),
            M.ACE.allow(role_developer, 'delete'),
            M.ACE.allow(role_admin, 'configure'),
            M.ACE.allow(role_admin, 'admin'),
        ]

    def uninstall(self, project):
        """Remove all the tool's artifacts from the database"""
        app_config_id = {'app_config_id': c.app.config._id}
        TM.Feedback.query.remove(app_config_id)
        super().uninstall(project)


class RootController(BaseController, FeedController):

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('jinja:forgefeedback:templates/feedback/index.html')
    def index(self, **kw):
        require_access(c.app, 'read')
        user_has_already_reviewed = False
        rating_by_user = Feedback.query.find({
            'reported_by_id': c.user._id, 'project_id': c.project._id}
        ).count()
        if rating_by_user > 0:
            user_has_already_reviewed = True
        return dict(review_list=self.get_review_list(),
                    user_has_already_reviewed=user_has_already_reviewed,
                    rating=c.project.rating)

    """ the list of all the feedbacks given by
    various users is listed on the index page """
    @expose('jinja:forgefeedback:templates/feedback/index.html')
    def get_review_list(self, **kw):
        self.review_list = Feedback.query.find({'project_id': c.project._id})\
                            .sort('created_date', pymongo.DESCENDING).all()
        return self.review_list

    """ The new feedback given by the logged in user which includes
    the review, rating, project id and the user id are all flushed
    into the database """
    @require_post()
    @expose('jinja:forgefeedback:templates/feedback/index.html')
    def create_feedback(self, description=None, rating=None, **kw):
        """saving the review for the first time """
        require_access(c.app, 'create')
        p = Feedback(description=description, rating=rating,
                     user_id=c.user._id, project_id=c.project._id)
        session(p).flush()
        flash('Feedback successfully added')
        M.main_orm_session.flush()
        g.director.create_activity(c.user, 'posted', p, related_nodes=[
                                   c.project], tags=['description'])
        self.getRating()  # force recalculation
        redirect(c.app.url)

    # called on click of the Feedback link
    @with_trailing_slash
    @expose('jinja:forgefeedback:templates/feedback/new_feedback.html')
    def new_feedback(self, **kw):
        require_access(c.app, 'create')
        return dict(action=c.app.config.url() + 'create')

    # called on click of edit review link and displays the previous feedback
    @expose('jinja:forgefeedback:templates/feedback/edit_feedback.html')
    def edit_feedback(self, **kw):
        self.review = Feedback.query.find(
                {'reported_by_id': c.user._id, 'project_id': c.project._id}
                ).first()
        return dict(description=self.review.description,
                    rating=self.review.rating)

    # The edited feedback will be updated in the index page
    @require_post()
    @expose('jinja:forgefeedback:templates/feedback/index.html')
    def edit_user_review(self, description=None, rating=None, **kw):
        Feedback.query.update(
            {'reported_by_id': c.user._id, 'project_id': c.project._id},
            {'$set': {'description': description, 'rating': rating}})
        self.rating = Feedback.query.find(
            {'reported_by_id': c.user._id, 'project_id': c.project._id})\
            .first()
        flash('Feedback successfully edited')
        g.director.create_activity(
            c.user, 'modified', self.rating,
            related_nodes=[c.project], tags=['description'])
        self.getRating()  # force recalculation
        redirect(c.app.url)

    # called when user clicks on delete link in feedback page
    @without_trailing_slash
    @require_post()
    @expose('jinja:forgefeedback:templates/feedback/index.html')
    def delete_feedback(self, **kw):
        user_review = Feedback.query.find(
            {'reported_by_id': c.user._id, 'project_id': c.project._id}
            ).first()
        if user_review:
            Feedback.query.remove(dict(
                {'reported_by_id': c.user._id, 'project_id': c.project._id}))
            M.main_orm_session.flush()
            self.getRating()  # force recalculation
            flash('Feedback successfully deleted')
            return 'Success'
        else:
            flash('Feedback was not deleted')
            return 'Failed'

    # This method is used to check for profanity in feedback text
    @expose()
    def feedback_check(self, description=None):
        pf = ProfanityFilter()
        if description:
            result = str(pf.is_profane(description)).lower()
        else:
            result = 'None'
        return result

    """ This method count the number of stars finds their sum and
    calculates the average of all the star rating count """
    def getRating(self, **kw):
        onestarcount = TM.Feedback.query.find(
            {'rating': '1', 'project_id': c.project._id}).count()
        twostarcount = TM.Feedback.query.find(
            {'rating': '2', 'project_id': c.project._id}).count()
        threestarcount = TM.Feedback.query.find(
            {'rating': '3', 'project_id': c.project._id}).count()
        fourstarcount = TM.Feedback.query.find(
            {'rating': '4', 'project_id': c.project._id}).count()
        fivestarcount = TM.Feedback.query.find(
            {'rating': '5', 'project_id': c.project._id}).count()
        sum_of_ratings = float(
            fivestarcount + fourstarcount + threestarcount + twostarcount +
            onestarcount)
        if sum_of_ratings != 0:
            average_user_ratings = float(
                (5*fivestarcount) + (4*fourstarcount) +
                (3*threestarcount) + (2*twostarcount) +
                (1*onestarcount)) / sum_of_ratings
            float_rating = float(average_user_ratings)
            int_rating = int(float_rating)
            float_point_value = float_rating - int_rating
            if float_point_value < 0.25:
                c.project.rating = int_rating
            elif float_point_value >= 0.25 < 0.75:
                c.project.rating = 0.5 + int_rating
            elif float_point_value >= 0.75:
                c.project.rating = float(int_rating)+1
            return average_user_ratings
        if sum_of_ratings == 0:
            c.project.rating = 0.0
