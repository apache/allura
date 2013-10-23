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
from pprint import pformat

import pkg_resources
from pylons import tmpl_context as c, app_globals as g
from pylons import request
from formencode import validators
from tg import expose, redirect, validate, response
from webob import exc

from allura import version
from allura.app import Application, SitemapEntry
from allura.lib import helpers as h
from allura.lib.helpers import DateTimeConverter
from allura.lib.security import require_access
from allura.lib.plugin import AuthenticationProvider
from allura.model import User, Feed, ACE, ProjectRole
from allura.controllers import BaseController
from allura.controllers.feed import FeedArgs, FeedController
from allura.lib.decorators import require_post

log = logging.getLogger(__name__)


class UserProfileApp(Application):
    __version__ = version.__version__
    installable = False
    tool_label = 'Profile'
    icons={
        24:'images/home_24.png',
        32:'images/home_32.png',
        48:'images/home_48.png'
    }

    def __init__(self, user, config):
        Application.__init__(self, user, config)
        self.root = UserProfileController()
        self.templates = pkg_resources.resource_filename(
            'allura.ext.user_profile', 'templates')

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        return [SitemapEntry('Profile', '.')]

    def admin_menu(self):
        return []

    def main_menu(self):
        return [SitemapEntry('Profile', '.')]

    def is_visible_to(self, user):
        # we don't work with user subprojects
        return c.project.is_root

    def install(self, project):
        pr = ProjectRole.by_user(c.user)
        if pr:
            self.config.acl = [
                ACE.allow(pr._id, perm)
                for perm in self.permissions ]

    def uninstall(self, project): # pragma no cover
        pass


class UserProfileController(BaseController, FeedController):

    def _check_security(self):
        require_access(c.project, 'read')

    @expose('jinja:allura.ext.user_profile:templates/user_index.html')
    def index(self, **kw):
        user = c.project.user_project_of
        if not user:
            raise exc.HTTPNotFound()
        provider = AuthenticationProvider.get(request)
        return dict(user=user, reg_date=provider.user_registration_date(user))

    def get_feed(self, project, app, user):
        """Return a :class:`allura.controllers.feed.FeedArgs` object describing
        the xml feed for this controller.

        Overrides :meth:`allura.controllers.feed.FeedController.get_feed`.

        """
        user = project.user_project_of
        return FeedArgs(
            {'author_link': user.url()},
            'Recent posts by %s' % user.display_name,
            project.url())
