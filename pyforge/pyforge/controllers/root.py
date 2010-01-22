# -*- coding: utf-8 -*-
"""Main Controller"""
import logging, string
from collections import defaultdict

import pkg_resources
from tg import expose, flash, redirect, session
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c, g

import ming

from pyforge.lib.base import BaseController
from pyforge.controllers.error import ErrorController
from pyforge.lib.dispatch import _dispatch
from pyforge import model as M
from .auth import AuthController
from .search import SearchController
from .static import StaticController
from .project import ProjectsController, HostProjectController

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
    projects = ProjectsController('projects/')
    users = ProjectsController('users/')

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

    def __call__(self, environ, start_response):
        """This is the basic WSGI callable that wraps and dispatches forge controllers.
        
        It peforms a number of functions: 
          * displays the forge index page
          * sets up and cleans up the Ming/MongoDB Session
          * persists all Ming object changes to Mongo
        """
        app = self._wsgi_handler(environ)
        if app is None:
            app = lambda e,s: BaseController.__call__(self, e, s)
        result = app(environ, start_response)
        if not isinstance(result, list):
            return self._cleanup_iterator(result)
        else:
            self._cleanup_request()
            return result

    def _cleanup_iterator(self, result):
        for x in result:
            yield x
        self._cleanup_request()

    def _cleanup_request(self):
        ming.orm.ormsession.ThreadLocalORMSession.flush_all()
        for msg in c.queued_messages:
            g._publish(**msg)
        ming.orm.ormsession.ThreadLocalORMSession.close_all()
        

    def _wsgi_handler(self, environ):
        host = environ['HTTP_HOST'].split(':')[0].lower()
        project = M.Project.query.get(_id=host + ':/')
        if project:
            return HostProjectController(project)
        if environ['PATH_INFO'].startswith('/_wsgi_/'):
            for ep in pkg_resources.iter_entry_points('pyforge'):
                App = ep.load()
                if App.wsgi.handles(environ): return App.wsgi

    @expose('pyforge.templates.index')
    @with_trailing_slash
    def index(self):
        """Handle the front-page."""
        projects = defaultdict(list)
        for p in M.Project.query.find(dict(is_root=True)):
            prefix, rest = p._id.split('/', 1)
            projects[prefix].append(p)
        return dict(projects=projects)

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)
        
