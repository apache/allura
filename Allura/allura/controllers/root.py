# -*- coding: utf-8 -*-

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

"""Main Controller"""
import logging

from tg import expose, request, config, session
from tg.decorators import with_trailing_slash
from tg.flash import TGFlash
from pylons import tmpl_context as c
from pylons import app_globals as g
from paste.deploy.converters import asbool

from allura.app import SitemapEntry
from allura.lib.base import WsgiDispatchController
from allura.lib import plugin
from allura.controllers.error import ErrorController
from allura import model as M
from allura.lib.widgets import project_list as plw
from .auth import AuthController
from .trovecategories import TroveCategoryController
from .search import SearchController, ProjectBrowseController
from .static import NewForgeController
from .site_admin import SiteAdminController
from .rest import RestController

__all__ = ['RootController']

log = logging.getLogger(__name__)

TGFlash.static_template = '''$('#messages').notify('%(message)s', {status: '%(status)s'});'''


class W:
    project_summary = plw.ProjectSummary()


class RootController(WsgiDispatchController):

    """
    The root controller for the allura application.

    All the other controllers and WSGI applications should be mounted on this
    controller. For example::

        panel = ControlPanelController()
        another_app = AnotherWSGIApplication()

    Keep in mind that WSGI applications shouldn't be mounted directly: They
    must be wrapped around with :class:`tg.controllers.WSGIAppController`.

    """

    auth = AuthController()
    error = ErrorController()
    nf = NewForgeController()
    search = SearchController()
    rest = RestController()
    categories = TroveCategoryController()

    def __init__(self):
        n_url_prefix = '/%s/' % request.path.split('/')[1]
        n = g.neighborhood_cache.get(n_url_prefix)
        if n and not n.url_prefix.startswith('//'):
            n.bind_controller(self)
        self.browse = ProjectBrowseController()
        self.nf.admin = SiteAdminController()

        super(RootController, self).__init__()

    def _setup_request(self):
        c.project = c.app = None
        c.user = plugin.AuthenticationProvider.get(request).authenticate_request()
        assert c.user is not None, ('c.user should always be at least User.anonymous(). '
                                    'Did you run `paster setup-app` to create the database?')
        if not c.user.is_anonymous():
            c.user.track_active(request)
            if asbool(config.get('force_ssl.logged_in')):
                session.secure = True

    def _cleanup_request(self):
        pass

    @expose('jinja:allura:templates/neighborhood_list.html')
    @with_trailing_slash
    def index(self, **kw):
        """Handle the front-page."""
        neighborhoods = M.Neighborhood.query.find().sort('name')
        categories = M.ProjectCategory.query.find(
            {'parent_id': None}).sort('name').all()
        c.custom_sidebar_menu = [
            SitemapEntry(cat.label, '/browse/' + cat.name) for cat in categories
        ]
        return dict(neighborhoods=neighborhoods, title="All Neighborhoods")
