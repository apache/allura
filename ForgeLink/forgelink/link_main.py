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

#-*- python -*-
import logging
import json

# Non-stdlib imports
from tg import expose, redirect, flash, jsonify
from pylons import tmpl_context as c
from pylons import request

# Pyforge-specific imports
from allura.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from allura.lib import helpers as h
from allura.lib.security import require_access
from allura.lib.utils import permanent_redirect
from allura import model as M
from allura.controllers import BaseController

# Local imports
from forgelink import version

log = logging.getLogger(__name__)


class ForgeLinkApp(Application):

    '''This is the Link app for PyForge'''
    __version__ = version.__version__
    permissions = ['configure', 'read']
    permissions_desc = {
        'read': 'View link.',
    }
    config_options = Application.config_options + [
        ConfigOption('url', str, None)
    ]
    searchable = True
    exportable = True
    tool_label = 'External Link'
    default_mount_label = 'Link name'
    default_mount_point = 'link'
    ordinal = 1
    icons = {
        24: 'images/ext_24.png',
        32: 'images/ext_32.png',
        48: 'images/ext_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = LinkAdminController(self)
        self.api_root = RootRestController(self)

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label
        return [SitemapEntry(menu_id, '.')[self.sidebar_menu()]]

    def sidebar_menu(self):
        return []

    def admin_menu(self):
        return super(ForgeLinkApp, self).admin_menu()

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project.name
        super(ForgeLinkApp, self).install(project)
        # Setup permissions
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_anon = M.ProjectRole.anonymous()._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_admin, 'configure'),
        ]

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        super(ForgeLinkApp, self).uninstall(project)

    def bulk_export(self, f):
        json.dump(RootRestController(self).link_json(),
                  f, cls=jsonify.GenericJSON, indent=2)


class RootController(BaseController):

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('jinja:forgelink:templates/link/index.html')
    def index(self, **kw):
        url = c.app.config.options.get('url')
        if url:
            permanent_redirect(url)
        return dict()

    @expose()
    def _lookup(self, *remainder):
        path = "/".join(remainder)
        url = c.app.config.options.get('url')
        if url:
            permanent_redirect(url + h.really_unicode(path).encode('utf-8'))
        return dict()


class LinkAdminController(DefaultAdminController):

    @expose()
    def index(self, **kw):
        flash('External link URL updated.')
        redirect(c.project.url() + 'admin/tools')


class RootRestController(BaseController):

    def __init__(self, app):
        self.app = app

    def _check_security(self):
        require_access(self.app, 'read')

    def link_json(self):
        return dict(url=self.app.config.options.get('url'))

    @expose('json:')
    def index(self, url='', **kw):
        if (request.method == 'POST') and (url != ''):
            require_access(self.app, 'configure')
            self.app.config.options.url = url
        return self.link_json()
