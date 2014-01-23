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
import calendar

from pylons import tmpl_context as c, app_globals as g
from pylons import request, response
from tg import expose, validate, config
from tg.decorators import with_trailing_slash, without_trailing_slash
from paste.deploy.converters import asbool, asint
from webob import exc
from webhelpers import feedgenerator as FG

from allura.app import Application
from allura import version
from allura.controllers import BaseController
from allura.lib.security import require_authenticated
from allura.model.timeline import perm_check
from allura.lib import helpers as h
from allura.lib.decorators import require_post
from allura.lib.widgets.form_fields import PageList
from allura.ext.user_profile import ProfileSectionBase

from .widgets.follow import FollowToggle

log = logging.getLogger(__name__)


class ForgeActivityApp(Application):

    """Project Activity page for projects."""
    __version__ = version.__version__
    default_mount_point = 'activity'
    max_instances = 0
    searchable = False

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = ForgeActivityController(self)
        self.api_root = ForgeActivityRestController(self)

    def admin_menu(self):  # pragma no cover
        return []

    def install(self, project):
        pass  # pragma no cover

    def uninstall(self, project):
        pass  # pragma no cover


class W:
    follow_toggle = FollowToggle()
    page_list = PageList()


class ForgeActivityController(BaseController):

    def __init__(self, app, *args, **kw):
        super(ForgeActivityController, self).__init__(*args, **kw)
        self.app = app
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)

    def _before(self, *args, **kw):
        """Runs before each request to this controller.

        """
        # register the custom css for our tool
        g.register_app_css('css/activity.css', app=self.app)

    def _get_activities_data(self, **kw):
        activity_enabled = config.get('activitystream.enabled', False)
        activity_enabled = request.cookies.get(
            'activitystream.enabled', activity_enabled)
        activity_enabled = asbool(activity_enabled)
        if not activity_enabled:
            raise exc.HTTPNotFound()

        c.follow_toggle = W.follow_toggle
        c.page_list = W.page_list
        if c.project.is_user_project:
            followee = c.project.user_project_of
            actor_only = followee != c.user
        else:
            followee = c.project
            actor_only = False

        following = g.director.is_connected(c.user, followee)
        timeline = g.director.get_timeline(followee, page=kw.get('page', 0),
                                           limit=kw.get('limit', 100),
                                           actor_only=actor_only,
                                           filter_func=perm_check(c.user))
        page = asint(kw.get('page', 0))
        limit = asint(kw.get('limit', 100))
        return dict(
            followee=followee,
            following=following,
            timeline=timeline,
            page=page,
            limit=limit,
            has_more=len(timeline) == limit)

    @expose('jinja:forgeactivity:templates/index.html')
    @with_trailing_slash
    def index(self, **kw):
        return self._get_activities_data(**kw)

    @expose('jinja:forgeactivity:templates/timeline.html')
    def pjax(self, **kw):
        return self._get_activities_data(**kw)

    @without_trailing_slash
    @expose()
    def feed(self, **kw):
        data = self._get_activities_data(**kw)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        d = {
            'title': 'Activity for %s' % data['followee'].shortname,
            'link': h.absurl(self.app.url),
            'description': 'Recent activity for %s' % data['followee'].shortname,
            'language': u'en',
        }
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed = FG.Atom1Feed(**d)
        else:
            feed = FG.Rss201rev2Feed(**d)
        for t in data['timeline']:
            url = h.absurl(t.obj.activity_url.encode('utf-8'))
            feed.add_item(title=u'%s %s %s%s' % (
                                t.actor.activity_name,
                t.verb,
                t.obj.activity_name,
                ' on %s' % t.target.activity_name if t.target.activity_name else '',
            ),
                link=url,
                pubdate=t.published,
                description=t.obj.activity_extras.get('summary'),
                unique_id=url,
                author_name=t.actor.activity_name,
                author_link=h.absurl(t.actor.activity_url))
        return feed.writeString('utf-8')

    @require_post()
    @expose('json:')
    @validate(W.follow_toggle)
    def follow(self, follow, **kw):
        activity_enabled = config.get('activitystream.enabled', False)
        activity_enabled = request.cookies.get(
            'activitystream.enabled', activity_enabled)
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


class ForgeActivityRestController(BaseController):

    def __init__(self, app, *args, **kw):
        super(ForgeActivityRestController, self).__init__(*args, **kw)
        self.app = app

    @expose('json:')
    def index(self, **kw):
        data = self.app.root._get_activities_data(**kw)
        return {
            'following': data['following'],
            'followee': {
                'activity_name': data['followee'].shortname,
                'activity_url': data['followee'].url(),
                'activity_extras': {},
            },
            'timeline': [{
                'published': calendar.timegm(a.published.timetuple()) * 1000,
                'actor': a.actor._deinstrument(),
                'verb': a.verb,
                'obj': a.obj._deinstrument(),
                'target': a.target._deinstrument(),
            } for a in data['timeline']],
        }


class ForgeActivityProfileSection(ProfileSectionBase):
    template = 'forgeactivity:templates/widgets/profile_section.html'

    def __init__(self, *a, **kw):
        super(ForgeActivityProfileSection, self).__init__(*a, **kw)
        self.activity_app = self.project.app_instance('activity')

    def check_display(self):
        app_installed = self.activity_app is not None
        activity_enabled = config.get('activitystream.enabled', False)
        activity_enabled = request.cookies.get(
            'activitystream.enabled', activity_enabled)
        activity_enabled = asbool(activity_enabled)
        return app_installed and activity_enabled

    def prepare_context(self, context):
        context.update({
            'user': self.user,
            'follow_toggle': W.follow_toggle,
            'following': g.director.is_connected(c.user, self.user),
            'timeline': g.director.get_timeline(
                self.user, page=0, limit=5,
                actor_only=True,
                filter_func=perm_check(c.user)),
            'activity_app': self.activity_app,
        })
        g.register_js('activity_js/follow.js')
        return context
