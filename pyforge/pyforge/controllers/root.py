# -*- coding: utf-8 -*-
"""Main Controller"""
import logging, string
from collections import defaultdict

import pkg_resources
from tg import expose, flash, redirect, session, config
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c, g
from webob import exc

import ew
import ming

from pyforge.lib.base import BaseController
from pyforge.controllers.error import ErrorController
from pyforge import model as M
from .auth import AuthController
from .search import SearchController
from .static import StaticController
from .project import NeighborhoodController, HostNeighborhoodController
from .oembed import OEmbedController

__all__ = ['RootController']

log = logging.getLogger(__name__)

class RootController(BaseController):
    """
    The root controller for the pyforge application.
    
    All the other controllers and WSGI applications should be mounted on this
    controller. For example::
    
        panel = ControlPanelController()
        another_app = AnotherWSGIApplication()
    
    Keep in mind that WSGI applications shouldn't be mounted directly: They
    must be wrapped around with :class:`tg.controllers.WSGIAppController`.
    
    """
    
    auth = AuthController()
    error = ErrorController()
    static = StaticController()
    search = SearchController()
    # projects = NeighborhoodController('Projects')
    # users = NeighborhoodController('Users', 'users/')
    # adobe = NeighborhoodController('Adobe')

    def __init__(self):
        """Create a user-aware root controller instance.
        
        The Controller is instantiated on each request before dispatch, 
        so c.user will always point to the current user.
        """
        # Lookup user
        uid = session.get('userid', None)
        c.project = c.app = None
        c.user = M.User.query.get(_id=uid) or M.User.anonymous()
        c.queued_messages = []
        for n in M.Neighborhood.query.find():
            if n.url_prefix.startswith('//'): continue
            n.bind_controller(self)
        self._ew_resources = ew.ResourceManager.get()

    def _cleanup_iterator(self, result):
        for x in result:
            yield x
        self._cleanup_request()

    def _cleanup_request(self):
        ming.orm.ormsession.ThreadLocalORMSession.flush_all()
        for msg in c.queued_messages:
            g._publish(**msg)
        ming.orm.ormsession.ThreadLocalORMSession.close_all()


    @expose('pyforge.templates.index')
    @with_trailing_slash
    def index(self):
        """Handle the front-page."""
        psort = [(n, M.Project.query.find(dict(is_root=True, neighborhood_id=n._id)).all())
                 for n in M.Neighborhood.query.find().sort('name')]
        return dict(projects=psort)
        
