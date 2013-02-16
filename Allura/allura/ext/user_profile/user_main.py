import logging
from pprint import pformat

import pkg_resources
from pylons import tmpl_context as c, app_globals as g
from pylons import request
from formencode import validators
from tg import expose, redirect, validate, response
from webob import exc

from allura import version
from allura.app import Application
from allura.lib import helpers as h
from allura.lib.helpers import DateTimeConverter
from allura.lib.security import require_access
from allura.model import User, Feed, ACE
from allura.controllers import BaseController
from allura.lib.decorators import require_post

log = logging.getLogger(__name__)


class UserProfileApp(Application):
    __version__ = version.__version__
    installable = False
    icons={
        24:'images/sftheme/24x24/home_24.png',
        32:'images/sftheme/32x32/home_32.png',
        48:'images/sftheme/48x48/home_48.png'
    }

    def __init__(self, user, config):
        Application.__init__(self, user, config)
        self.root = UserProfileController()
        self.templates = pkg_resources.resource_filename(
            'allura.ext.user_profile', 'templates')

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        return []

    def admin_menu(self):
        return []

    def install(self, project):
        pr = c.user.project_role()
        if pr:
            self.config.acl = [
                ACE.allow(pr._id, perm)
                for perm in self.permissions ]

    def uninstall(self, project): # pragma no cover
        pass


class UserProfileController(BaseController):

    def _check_security(self):
        require_access(c.project, 'read')

    @expose('jinja:allura.ext.user_profile:templates/user_index.html')
    def index(self, **kw):
        user = c.project.user_project_of
        if not user:
            raise exc.HTTPNotFound()
        if g.show_userstats and user.stats.visible:
            from forgeuserstats.main import ForgeUserStatsApp
            link, description = ForgeUserStatsApp.createlink(user)
        else:
            link, description = None, None
        return dict(user=user,
                    statslinkurl = link,
                    statslinkdescription = description)
    # This will be fully implemented in a future iteration
    # @expose('jinja:allura.ext.user_profile:templates/user_subscriptions.html')
    # def subscriptions(self):
    #     username = c.project.shortname.split('/')[1]
    #     user = User.by_username(username)
    #     subs = Subscriptions.query.find({'user_id':user._id}).all()
    #     for sub in subs:
    #         for s in sub.subscriptions:
    #             r = g.solr_short_timeout.search(s.artifact_index_id)
    #             print r.docs
    #     return dict(user=user)

    @expose()
    @validate(dict(
            since=DateTimeConverter(if_empty=None),
            until=DateTimeConverter(if_empty=None),
            page=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, page=None, limit=None, **kw):
        user = c.project.user_project_of
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent posts by %s' % user.display_name
        feed = Feed.feed(
            {'author_link':user.url()},
            feed_type,
            title,
            c.project.url(),
            title,
            since, until, page, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')
