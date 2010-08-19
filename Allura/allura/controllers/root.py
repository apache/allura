# -*- coding: utf-8 -*-
"""Main Controller"""
import logging, string, os
from collections import defaultdict

import pkg_resources
from tg import expose, flash, redirect, session, config, response, request
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c, g, cache

import ew
import ming

import allura
from allura.app import SitemapEntry
from allura.lib.base import BaseController
from allura.lib import helpers as h
from allura.lib import plugin
from allura.controllers.error import ErrorController
from allura import model as M
from allura.lib.widgets import project_list as plw
from .auth import AuthController
from .search import SearchController, ProjectBrowseController
from .static import NewForgeController
from .project import NeighborhoodController, HostNeighborhoodController
from .oembed import OEmbedController
from .rest import RestController

__all__ = ['RootController']

log = logging.getLogger(__name__)

class W:
    project_summary = plw.ProjectSummary()

class RootController(BaseController):
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

    def __init__(self):
        for n in M.Neighborhood.query.find():
            if n.url_prefix.startswith('//'): continue
            n.bind_controller(self)
        self.browse = ProjectBrowseController()
        super(RootController, self).__init__()

    def _setup_request(self):
        c.project = c.app = None
        c.user = plugin.AuthenticationProvider.get(request).authenticate_request()
        assert c.user is not None, 'c.user should always be at least User.anonymous()'
        c.queued_messages = []

    @expose('allura.templates.project_list')
    @with_trailing_slash
    def index(self, **kw):
        """Handle the front-page."""
        c.project_summary = W.project_summary
        projects = M.Project.query.find(
            dict(is_root=True,
                 shortname={'$ne':'--init--'},
                 deleted=False)).sort('shortname').all()
        neighborhoods = M.Neighborhood.query.find().sort('name')
        psort = [ (n, [ p for p in projects if p.neighborhood_id==n._id ])
                  for n in neighborhoods ]
        categories = M.ProjectCategory.query.find({'parent_id':None}).sort('name').all()
        c.custom_sidebar_menu = [
            SitemapEntry(cat.label, '/browse/'+cat.name, className='nav_child') for cat in categories
        ]
        return dict(projects=psort,title="All Projects",text=None)
