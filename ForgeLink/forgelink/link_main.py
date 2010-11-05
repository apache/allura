#-*- python -*-
import logging

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, response
from pylons import g, c, request

from pymongo.bson import ObjectId

# Pyforge-specific imports
from allura.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from allura.lib import helpers as h
from allura.lib.security import require, has_artifact_access
from allura.model import ProjectRole
from allura.controllers import BaseController

# Local imports
from forgelink import version

log = logging.getLogger(__name__)


class ForgeLinkApp(Application):
    '''This is the Link app for PyForge'''
    __version__ = version.__version__
    permissions = [ 'configure', 'read' ]
    config_options = Application.config_options + [
        ConfigOption('url', str, None)
    ]
    searchable=True
    tool_label='External Link'
    default_mount_label='Link name'
    default_mount_point='link'
    ordinal=1

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = LinkAdminController(self)

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        return [SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def sidebar_menu(self):
        return []

    def admin_menu(self):
        return super(ForgeLinkApp, self).admin_menu()

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project.name
        super(ForgeLinkApp, self).install(project)
        # Setup permissions
        role_anon = ProjectRole.anonymous()._id
        self.config.acl.update(
            configure=c.project.acl['tool'],
            read=[role_anon])

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        super(ForgeLinkApp, self).uninstall(project)

class RootController(BaseController):

    def _check_security(self):
        require(has_artifact_access('read'))

    @expose('jinja:link/index.html')
    def index(self, **kw):
        url = c.app.config.options.get('url')
        if url:
            redirect(url)
        return dict()

class LinkAdminController(DefaultAdminController):

    @expose()
    def index(self, **kw):
        redirect('options')
