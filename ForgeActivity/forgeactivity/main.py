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

from pylons import tmpl_context as c, app_globals as g
from pylons import request
from tg import expose, validate, config
from tg.decorators import with_trailing_slash
from paste.deploy.converters import asbool
from webob import exc

from allura.app import Application
from allura import version
from allura.controllers import BaseController
from allura.lib.security import require_authenticated
from allura.model.timeline import perm_check

from .widgets.follow import FollowToggle

log = logging.getLogger(__name__)


class ForgeActivityApp(Application):
    """Project Activity page for projects."""
    __version__ = version.__version__
    default_mount_point = 'activity'
    installable = False
    searchable = False

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = ForgeActivityController(self)

    def admin_menu(self): # pragma no cover
        return []

    def install(self, project):
        pass # pragma no cover

    def uninstall(self, project):
        pass # pragma no cover

class W:
    follow_toggle = FollowToggle()

class ForgeActivityController(BaseController):
    def __init__(self, app, *args, **kw):
        super(ForgeActivityController, self).__init__(*args, **kw)
        self.app = app

    def _before(self, *args, **kw):
        """Runs before each request to this controller.

        """
        # register the custom css for our tool
        g.register_app_css('css/activity.css', app=self.app)

    @expose('jinja:forgeactivity:templates/index.html')
    @with_trailing_slash
    def index(self, **kw):
        activity_enabled = config.get('activitystream.enabled', False)
        activity_enabled = request.cookies.get('activitystream.enabled', activity_enabled)
        activity_enabled = asbool(activity_enabled)
        if not activity_enabled:
            raise exc.HTTPNotFound()

        c.follow_toggle = W.follow_toggle
        if c.project.is_user_project:
            followee = c.project.user_project_of
            actor_only = followee != c.user
        else:
            followee = c.project
            actor_only = False

        following = g.director.is_connected(c.user, followee)
        timeline = g.director.get_timeline(followee, page=kw.get('page', 0),
                limit=kw.get('limit', 100), actor_only=actor_only,
                filter_func=perm_check(c.user))
        return dict(followee=followee, following=following, timeline=timeline)

    @expose('json:')
    @validate(W.follow_toggle)
    def follow(self, follow, **kw):
        activity_enabled = config.get('activitystream.enabled', False)
        activity_enabled = request.cookies.get('activitystream.enabled', activity_enabled)
        activity_enabled = asbool(activity_enabled)
        if not activity_enabled:
            raise exc.HTTPNotFound()

        require_authenticated()
        followee = c.project
        if c.project.is_user_project:
            followee = c.project.user_project_of
        if c.user == followee:
            return dict(
                success=False,
                message='Cannot follow yourself')
        try:
            if follow:
                g.director.connect(c.user, followee)
            else:
                g.director.disconnect(c.user, followee)
        except Exception as e:
            log.exception('Unexpected error following user')
            return dict(
                success=False,
                message='Unexpected error: %s' % e)
        return dict(
            success=True,
            message=W.follow_toggle.success_message(follow),
            following=follow)
