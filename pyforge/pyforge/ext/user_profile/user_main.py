import os
import difflib
import logging
from pprint import pformat

import pkg_resources
from pylons import c, request
from tg import expose, redirect, flash
from webob import exc
from pymongo.bson import ObjectId


from pyforge import version
from pyforge.app import Application, WidgetController, ConfigOption, SitemapEntry
from pyforge.lib import helpers as h
from pyforge.ext.project_home import model as M
from pyforge.lib.security import require, has_project_access, has_artifact_access
from pyforge.model import User

log = logging.getLogger(__name__)

class UserWidgets(WidgetController):
    widgets=['welcome']

    def __init__(self, app): pass

    def welcome(self):
        return self.portlet('<p>Please configure your widgets </p>')

class UserProfileApp(Application):
    __version__ = version.__version__
    widget = UserWidgets
    installable = False

    def __init__(self, user, config):
        Application.__init__(self, user, config)
        self.root = UserProfileController()
        self.templates = pkg_resources.resource_filename(
            'pyforge.ext.user_profile', 'templates')

    @property
    def sitemap(self):
        menu_id = 'User'
        return []

    def sidebar_menu(self):
        return [ SitemapEntry('Preferences', '/auth/prefs/')]

    def admin_menu(self):
        return []

    # @property
    # def templates(self):
    #     return

    def install(self, project):
        pr = c.user.project_role()
        if pr:
            for perm in self.permissions:
                self.config.acl[perm] = [ pr._id ]

    def uninstall(self, project): # pragma no cover
        raise NotImplementedError, "uninstall"

class UserProfileController(object):

    def _check_security(self):
        require(has_project_access('read'),
                'Read access required')

    @expose('pyforge.ext.user_profile.templates.user_index')
    def index(self):
        username = c.project.shortname.split('/')[1]
        user = User.by_username(username)
        return dict(user=user)

    @expose('pyforge.ext.user_profile.templates.user_dashboard_configuration')
    def configuration(self):
        username = c.project.shortname.split('/')[1]
        user = User.by_username(username)
        return dict(user=user)

    @h.vardec
    @expose()
    def update_configuration(self, divs=None, layout_class=None, new_div=None, **kw):
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

    @expose('json')
    def permissions(self, repo_path=None, **kw):
        """Expects repo_path to be a filesystem path like
        '/git/p/mygreatproject/reponame.git', or
        '/svn/adobe/someproject/subproject/reponame/'.

        Explicitly: (1) The path starts with a containing directory,
        e.g., /git, which is not relevant.  (2) The final component of
        the path is the repo name, and may include a trailing slash.
        Less a '.git' suffix, the repo name _is_ the mount point.
        (3) Everything between the containing directory and the repo is
        an exact match for a project URL.  Multiple components
        signify sub-projects.

        Note that project and user _names_ are built with slashes, but
        the supplied repo_path will use the os file separator character.
        We know we'll get a user from our query because we're at that
        user's profile page.

        Returns JSON describing this user's permissions on that repo.
        """

        username = c.project.shortname.split('/')[1]
        user = User.by_username(username)
        parts = [p for p in repo_path.split(os.path.sep) if p]
        project_path = '/' + '/'.join(parts[1:])
        project, rest = h.find_project(project_path)
        mount_point = os.path.splitext(parts[-1])[0]
        c.project = project
        c.app = project.app_instance(mount_point)
        return dict(allow_read=has_artifact_access('read')(user=user),
                    allow_write=has_artifact_access('write')(user=user),
                    allow_create=has_artifact_access('create')(user=user))
