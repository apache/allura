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

import pkg_resources
from tg import tmpl_context as c
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
    tool_label = 'home'
    default_mount_label = 'Project Home'
    max_instances = 0
    icons = {
        24: 'images/home_24.png',
        32: 'images/home_32.png',
        48: 'images/home_48.png'
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
        return [SitemapEntry(
            self.config.options.mount_label,
            '..')]

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        return [
            SitemapEntry('Home', '..')]

    @h.exceptionless([], log)
    def sidebar_menu(self):
        return []

    def admin_menu(self):
        return []

    def install(self, project):
        super().install(project)
        pr = model.ProjectRole.by_user(c.user)
        if pr:
            self.config.acl = [
                model.ACE.allow(pr._id, perm)
                for perm in self.permissions]


class ProjectHomeController(BaseController):

    @with_trailing_slash
    @expose()
    def index(self, **kw):
        redirect('..')
