#-*- python -*-
import logging

import pkg_resources
from tg import expose, redirect, validate
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c, g

from pyforge.app import Application, SitemapEntry, DefaultAdminController
from pyforge import model as M
from pyforge.lib import helpers as h

from . import version
from . import widgets
from . import model as SM

log = logging.getLogger(__name__)

class W:
    admin_list = widgets.ListAdmin()
    new_list = widgets.NewList()

class MailmanApp(Application):
    '''This is the Mailing List app for PyForge'''
    __version__ = version.__version__
    permissions = [ 'configure', 'admin']
    searchable=True
    installable = True
    tool_label='Mailing List'
    default_mount_label='List'
    default_mount_point='list'
    ordinal=7
    sitemap = []
    api_root=None
    root=None

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        # self.root = RootController()
        # self.api_root = RootRestController()
        self.admin = MailmanAdminController(self)

    def has_access(self, user, topic):
        return False

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = [SitemapEntry('Admin Lists', admin_url, className='nav_child') ]
        return links

    def sidebar_menu(self):
        return []

    @property
    def templates(self):
         return pkg_resources.resource_filename('sfx', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'
        super(MailmanApp, self).install(project)
        # Setup permissions
        self.config.acl.update(
            configure=c.project.acl['tool'],
            admin=c.project.acl['tool'])

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        super(MailmanApp, self).uninstall(project)

class MailmanAdminController(DefaultAdminController):

    def __init__(self, app):
        self.app = app

    @with_trailing_slash
    @expose('sfx.templates.admin_main')
    def index(self, **kw):
        c.list = W.admin_list
        c.new = W.new_list
        return dict(lists=list(SM.List.find()))

    @expose()
    @validate(form=W.new_list)
    def create(self, name=None, **kw):
        lst = SM.List(c.project.shortname + '-' + name)
        lst.create(**kw)
        redirect('.')

    @expose()
    @h.vardec
    @validate(form=W.admin_list)
    def save(self, lists=None, **kw):
        if lists is None: lists = []
        for args in lists:
            lst = SM.List(args['name'])
            lst.update(
                description = args['description'],
                is_public = args['is_public'])
            if args['is_public'] == SM.List.DELETE:
                lst.delete()
        redirect('.')
