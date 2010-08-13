#-*- python -*-
import logging

import pkg_resources
from tg import expose, redirect, validate
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c, g

from allura.app import Application, SitemapEntry, DefaultAdminController
from allura import model as M
from allura.lib import helpers as h

from . import version
from . import widgets
from . import model as SM

log = logging.getLogger(__name__)

class W:
    admin_list = widgets.ListAdmin()
    new_list = widgets.NewList()

class SFXBaseApp(Application):
    '''Base class for admin-only SFX resources'''
    __version__ = version.__version__
    permissions = [ 'configure', 'admin']
    searchable=False
    installable = True
    tool_label=''
    default_mount_label=''
    default_mount_point='sfx-app'
    ordinal=8
    sitemap = []
    api_root=None
    root=None
    AdminController=None

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.admin = self.AdminController(self)

    def has_access(self, user, topic):
        return False

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = [SitemapEntry('Admin %s' % self.tool_label, admin_url, className='nav_child') ]
        return links

    def sidebar_menu(self):
        return []

    @property
    def templates(self):
         return pkg_resources.resource_filename('sfx', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'
        super(SFXBaseApp, self).install(project)
        # Setup permissions
        self.config.acl.update(
            read=c.project.acl['read'],
            configure=c.project.acl['tool'],
            admin=c.project.acl['tool'])

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        super(SFXBaseApp, self).uninstall(project)
