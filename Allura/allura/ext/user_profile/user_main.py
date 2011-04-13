import os
import logging
from pprint import pformat

import pkg_resources
from pylons import c, request
from formencode import validators
from tg import expose, redirect, validate, response

from allura import version
from allura.app import Application, WidgetController, SitemapEntry
from allura.lib import helpers as h
from allura.lib.helpers import DateTimeConverter
from allura.ext.project_home import model as M
from allura.lib.security import require, has_access, require_access
from allura.model import User, Notification, ACE
from allura.controllers import BaseController
from allura.lib.decorators import require_post

log = logging.getLogger(__name__)

class UserWidgets(WidgetController):
    widgets=['welcome']

    def __init__(self, app): pass

    def welcome(self):
        return self.portlet('<p><!-- Please configure your widgets --></p>')

class UserProfileApp(Application):
    __version__ = version.__version__
    widget = UserWidgets
    installable = False

    def __init__(self, user, config):
        Application.__init__(self, user, config)
        self.root = UserProfileController()
        self.templates = pkg_resources.resource_filename(
            'allura.ext.user_profile', 'templates')

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        return []

    @h.exceptionless([], log)
    def sidebar_menu(self):
        return [ SitemapEntry('Preferences', '/auth/prefs/')]

    def admin_menu(self):
        return []

    def install(self, project):
        pr = c.user.project_role()
        if pr:
            self.config.acl = [
                ACE.allow(pr._id, perm)
                for perm in self.permissions ]

    def uninstall(self, project): # pragma no cover
        raise NotImplementedError, "uninstall"

class UserProfileController(BaseController):

    def _check_security(self):
        require_access(c.project, 'read')

    @expose('jinja:allura.ext.user_profile:templates/user_index.html')
    def index(self, **kw):
        username = c.project.shortname.split('/')[1]
        user = User.by_username(username)
        return dict(user=user)
    # This will be fully implemented in a future iteration
    # @expose('jinja:allura.ext.user_profile:templates/user_subscriptions.html')
    # def subscriptions(self):
    #     username = c.project.shortname.split('/')[1]
    #     user = User.by_username(username)
    #     subs = Subscriptions.query.find({'user_id':user._id}).all()
    #     for sub in subs:
    #         for s in sub.subscriptions:
    #             r = g.solr.search(s.artifact_index_id)
    #             print r.docs
    #     return dict(user=user)

    @expose('jinja:allura.ext.user_profile:templates/user_dashboard_configuration.html')
    def configuration(self):
        username = c.project.shortname.split('/')[1]
        user = User.by_username(username)
        return dict(user=user)

    @expose()
    @validate(dict(
            since=DateTimeConverter(if_empty=None),
            until=DateTimeConverter(if_empty=None),
            page=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, page=None, limit=None):
        username = c.project.shortname.split('/')[1]
        user = User.by_username(username)
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent posts by %s' % user.display_name
        feed = Notification.feed(
            {'author_id':user._id},
            feed_type,
            title,
            c.project.url(),
            title,
            since, until, page, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

    @h.vardec
    @expose()
    @require_post()
    def update_configuration(self, divs=None, layout_class=None, new_div=None, **kw):
        require_access(c.project, 'update')
        config = M.PortalConfig.current()
        config.layout_class = layout_class
        # Handle updated and deleted divs
        if divs is None: divs = []
        new_divs = []
        for div in divs:
            log.info('Got div update:%s', pformat(div))
            if div.get('del'): continue
            new_divs.append(div)
        # Handle new divs
        if new_div:
            new_divs.append(dict(name=h.nonce(), content=[]))
        config.layout = []
        for div in new_divs:
            content = []
            for w in div.get('content', []):
                if w.get('del'): continue
                mp,wn = w['widget'].split('/')
                content.append(dict(mount_point=mp, widget_name=wn))
            if div.get('new_widget'):
                content.append(dict(mount_point='profile', widget_name='welcome'))
            config.layout.append(dict(
                    name=div['name'],
                    content=content))
        redirect('configuration')


    @expose('json:')
    def permissions(self, repo_path=None, **kw):
        """Expects repo_path to be a filesystem path like
            <tool>/<project>.<neighborhood>/reponame[.git]
        unless the <neighborhood> is 'p', in which case it is
            <tool>/<project>/reponame[.git]

        Returns JSON describing this user's permissions on that repo.
        """
        if not repo_path:
            return {"error":"no path specified"}
        disallow = dict(allow_read=False, allow_write=False, allow_create=False)
        # Find the user
        username = c.project.shortname.split('/')[1]
        user = User.by_username(username)

        parts = [p for p in repo_path.split(os.path.sep) if p]
        # strip the tool name
        parts = parts[1:]
        if '.' in parts[0]:
            project, neighborhood = parts[0].split('.')
        else:
            project, neighborhood = parts[0], 'p'
        parts = [ neighborhood, project ] + parts[1:]
        project_path = '/' + '/'.join(parts)
        project, rest = h.find_project(project_path)
        if project is None:
            log.info("Can't find project at %s from repo_path %s",
                     project_path, repo_path)
            return disallow
        mount_point = os.path.splitext(rest[0])[0]
        c.project = project
        c.app = project.app_instance(mount_point)
        if c.app is None:
            log.info("Can't find repo at %s on repo_path %s",
                     mount_point, repo_path)
            return disallow
        return dict(allow_read=has_access(c.app, 'read')(user=user),
                    allow_write=has_access(c.app, 'write')(user=user),
                    allow_create=has_access(c.app, 'create')(user=user))
