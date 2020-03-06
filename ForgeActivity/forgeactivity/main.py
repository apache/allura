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
import logging
import calendar
from datetime import timedelta
from itertools import islice

from bson import ObjectId
from ming.orm import session
from tg import tmpl_context as c, app_globals as g
from tg import request, response
from tg import expose, validate, config
from tg.decorators import with_trailing_slash, without_trailing_slash
from paste.deploy.converters import asbool, asint
from webob import exc
import feedgenerator as FG
from activitystream.storage.mingstorage import Activity

from allura.app import Application
from allura import version
from allura import model as M
from allura.controllers import BaseController
from allura.controllers.rest import AppRestControllerMixin
from allura.lib.security import require_authenticated, require_access
from allura.model.timeline import perm_check, get_activity_object
from allura.lib import helpers as h
from allura.lib.decorators import require_post
from allura.lib.widgets.form_fields import PageList
from allura.ext.user_profile import ProfileSectionBase

from .widgets.follow import FollowToggle
from six.moves import filter

log = logging.getLogger(__name__)


class ForgeActivityApp(Application):

    """Project Activity page for projects."""
    __version__ = version.__version__
    default_mount_point = 'activity'
    max_instances = 0
    searchable = False
    has_notifications = False

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = ForgeActivityController(self)
        self.api_root = ForgeActivityRestController(self)

    def admin_menu(self):  # pragma no cover
        return []

    def install(self, project):
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
        ]

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

    def _check_security(self):
        require_access(c.app, 'read')

    def _before(self, *args, **kw):
        """Runs before each request to this controller.

        """
        # register the custom css for our tool
        g.register_app_css('css/activity.css', app=self.app)

    def _get_activities_data(self, **kw):
        activity_enabled = asbool(config.get('activitystream.enabled', False))
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
        limit, page = h.paging_sanitizer(kw.get('limit', 100), kw.get('page', 0))
        extra_limit = limit
        # get more in case perm check filters some out
        if page == 0 and limit <= 10:
            extra_limit = limit * 20
        timeline = g.director.get_timeline(followee, page,
                                           limit=extra_limit,
                                           actor_only=actor_only)
        filtered_timeline = list(islice(filter(perm_check(c.user), timeline),
                                        0, limit))
        if extra_limit == limit:
            # if we didn't ask for extra, then we expect there's more if we got all we asked for
            has_more = len(timeline) == limit
        else:
            # if we did ask for extra, check filtered result
            has_more = len(filtered_timeline) == limit
        return dict(
            followee=followee,
            following=following,
            timeline=filtered_timeline,
            page=page,
            limit=limit,
            has_more=has_more,
            actor_only=actor_only)

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
        response.headers['Content-Type'] = str('')
        response.content_type = str('application/xml')
        d = {
            'title': 'Activity for %s' % data['followee'].activity_name,
            'link': h.absurl(self.app.url),
            'description': 'Recent activity for %s' % (
                data['followee'].activity_name),
            'language': 'en',
        }
        if request.environ['PATH_INFO'].endswith(str('.atom')):
            feed = FG.Atom1Feed(**d)
        else:
            feed = FG.Rss201rev2Feed(**d)
        for t in data['timeline']:
            url_id = h.absurl(t.obj.activity_url)  # try to keep this consistent over time (not url-quoted)
            url = h.absurl(h.urlquote_path_only(t.obj.activity_url))
            feed.add_item(title='%s %s %s%s' % (
                                t.actor.activity_name,
                t.verb,
                t.obj.activity_name,
                ' on %s' % t.target.activity_name if t.target.activity_name else '',
            ),
                link=url,
                pubdate=t.published,
                description=t.obj.activity_extras.get('summary'),
                unique_id=url_id,
                author_name=t.actor.activity_name,
                author_link=h.absurl(t.actor.activity_url))
        return feed.writeString('utf-8')

    @require_post()
    @expose('json:')
    @validate(W.follow_toggle)
    def follow(self, follow, **kw):
        activity_enabled = asbool(config.get('activitystream.enabled', False))
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

    @require_post()
    @expose('json:')
    def delete_item(self, activity_id, **kwargs):
        require_access(c.project.neighborhood, 'admin')
        activity = Activity.query.get(_id=ObjectId(activity_id))
        if not activity:
            raise exc.HTTPGone
        # find other copies of this activity on other user/projects timelines
        # but only within a small time window, so we can do efficient searching
        activity_ts = activity._id.generation_time
        time_window = timedelta(hours=1)
        all_copies = Activity.query.find({
            '_id': {
                '$gt': ObjectId.from_datetime(activity_ts - time_window),
                '$lt': ObjectId.from_datetime(activity_ts + time_window),
            },
            'obj': activity.obj,
            'target': activity.target,
            'actor': activity.actor,
            'verb': activity.verb,
            'tags': activity.tags,
        }).all()
        log.info('Deleting %s copies of activity record: %s %s %s', len(all_copies),
                 activity.actor.activity_url, activity.verb, activity.obj.activity_url)
        for activity in all_copies:
            activity.query.delete()
        return {'success': True}


class ForgeActivityRestController(BaseController, AppRestControllerMixin):

    def __init__(self, app, *args, **kw):
        super(ForgeActivityRestController, self).__init__(*args, **kw)
        self.app = app

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('json:')
    def index(self, **kw):
        data = self.app.root._get_activities_data(**kw)
        return {
            'following': data['following'],
            'followee': {
                'activity_name': data['followee'].activity_name,
                'activity_url': data['followee'].url(),
                'activity_extras': {},
            },
            'timeline': [{
                'published': calendar.timegm(a.published.timetuple()) * 1000,
                'actor': a.actor._deinstrument(),
                'verb': a.verb,
                'obj': a.obj._deinstrument(),
                'target': a.target._deinstrument(),
                'tags': a.tags._deinstrument(),
            } for a in data['timeline']],
        }


class ForgeActivityProfileSection(ProfileSectionBase):
    template = 'forgeactivity:templates/widgets/profile_section.html'

    def __init__(self, *a, **kw):
        super(ForgeActivityProfileSection, self).__init__(*a, **kw)
        self.activity_app = self.project.app_instance('activity')

    def check_display(self):
        app_installed = self.activity_app is not None
        activity_enabled = asbool(config.get('activitystream.enabled', False))
        return app_installed and activity_enabled

    def prepare_context(self, context):
        full_timeline = g.director.get_timeline(
            self.user, page=0, limit=100,
            actor_only=True,
        )
        filtered_timeline = list(islice(filter(perm_check(c.user), full_timeline),
                                        0, 8))
        for activity in filtered_timeline:
            # Get the project for the activity.obj so we can use it in the
            # template. Expunge first so Ming doesn't try to flush the attr
            # we create to temporarily store the project.
            #
            # The get_activity_object() calls are cheap, pulling from
            # the session identity map instead of mongo since identical
            # calls are made by perm_check() above.
            session(activity).expunge(activity)
            activity_obj = get_activity_object(activity.obj)
            activity.obj.project = getattr(activity_obj, 'project', None)

        context.update({
            'follow_toggle': W.follow_toggle,
            'following': g.director.is_connected(c.user, self.user),
            'timeline': filtered_timeline,
            'activity_app': self.activity_app,
        })
        g.register_js('activity_js/follow.js')
        return context
