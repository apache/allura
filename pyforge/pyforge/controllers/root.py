# -*- coding: utf-8 -*-
"""Main Controller"""
import logging, string
from collections import defaultdict

import pkg_resources
from tg import expose, flash, redirect, session
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c

import ming

from pyforge.lib.base import BaseController
from pyforge.controllers.error import ErrorController
from pyforge.lib.dispatch import _dispatch
from pyforge import model as M
from .auth import AuthController
from .search import SearchController
from .static import StaticController
from .project import ProjectsController

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
        # Lookup user
        uid = session.get('userid', None)
        c.user = M.User.m.get(_id=uid) or M.User.anonymous

    def __call__(self, environ, start_response):
        app = self._wsgi_handler(environ)
        if app is None:
            app = lambda e,s: BaseController.__call__(self, e, s)
        result = app(environ, start_response)
        if not isinstance(result, list):
            return self._session_closing_iterator(result)
        else:
            # Clear all the Ming thread-local sessions
            ming.orm.ormsession.ThreadLocalORMSession.close_all()
            return result

    def _session_closing_iterator(self, result):
        for x in result:
            yield x
        ming.orm.ThreadLocalORMSession.close_all()

    def _wsgi_handler(self, environ):
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
        


