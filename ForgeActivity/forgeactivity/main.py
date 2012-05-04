import logging

import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pylons import c, g, request
from tg import expose, validate, config
from tg.decorators import with_trailing_slash
from paste.deploy.converters import asbool
from webob import exc

from allura.app import Application
from allura import version
from allura.controllers import BaseController
from allura.lib.security import require_authenticated

from activitystream import director

from .widgets.follow import FollowToggle

log = logging.getLogger(__name__)


class ForgeActivityApp(Application):
    """Project Activity page for projects."""
    __version__ = version.__version__
    default_mount_point = 'activity'
    installable = False
    searchable = False
    hidden = True
    sitemap=[]

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = ForgeActivityController()

    def main_menu(self): # pragma no cover
        return []

    def sidebar_menu(self): # pragma no cover
        return []

    def admin_menu(self): # pragma no cover
        return []

    def install(self, project):
        pass # pragma no cover

    def uninstall(self, project):
        pass # pragma no cover

class W:
    follow_toggle = FollowToggle()

class ForgeActivityController(BaseController):
    @expose('jinja:forgeactivity:templates/index.html')
    @with_trailing_slash
    def index(self, **kw):
        activity_enabled = config.get('activitystream.enabled', False)
        activity_enabled = request.cookies.get('activitystream.enabled', activity_enabled)
        activity_enabled = asbool(activity_enabled)
        if not activity_enabled:
            raise exc.HTTPNotFound()

        c.follow_toggle = W.follow_toggle
        followee = c.project
        timeline = []
        if c.project.is_user_project:
            followee = c.project.user_project_of
            if followee == c.user:
                # user is looking at his own activity stream
                timeline = g.director.create_timeline(c.user)
        following = g.director.is_connected(c.user, followee)

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
            return dict(
                success=False,
                message='Unexpected error: %s' % e)
        return dict(
            success=True,
            message=W.follow_toggle.success_message(follow),
            following=follow)
