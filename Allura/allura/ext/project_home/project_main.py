import logging

import pkg_resources
from pylons import c
from tg import expose, redirect
from tg.decorators import with_trailing_slash

from allura import version
from allura.app import Application, SitemapEntry
from allura.lib import helpers as h
from allura.controllers import BaseController
from allura import model


log = logging.getLogger(__name__)


class ProjectHomeApp(Application):
    __version__ = version.__version__
    installable = False
    tool_label = 'home'
    default_mount_label='Project Home'
    icons={
        24:'images/home_24.png',
        32:'images/home_32.png',
        48:'images/home_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = ProjectHomeController()
        self.templates = pkg_resources.resource_filename(
            'allura.ext.project_home', 'templates')

    def is_visible_to(self, user):
        '''Whether the user can view the app.'''
        return True

    def main_menu(self):
        '''Apps should provide their entries to be added to the main nav
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        '''
        return [ SitemapEntry(
                self.config.options.mount_label.title(),
                '..')]

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = 'Home'
        return [
            SitemapEntry('Home', '..') ]

    @h.exceptionless([], log)
    def sidebar_menu(self):
        return [ ]

    def admin_menu(self):
        return []

    def install(self, project):
        super(ProjectHomeApp, self).install(project)
        pr = c.user.project_role()
        if pr:
            self.config.acl = [
                model.ACE.allow(pr._id, perm)
                for perm in self.permissions ]


class ProjectHomeController(BaseController):

    @with_trailing_slash
    @expose()
    def index(self, **kw):
        redirect('..')
