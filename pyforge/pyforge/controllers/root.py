# -*- coding: utf-8 -*-
"""Main Controller"""
import logging

from tg import expose, flash, redirect, session
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c
from webob import exc

from pyforge.lib.base import BaseController
from pyforge.controllers.error import ErrorController

from pyforge.lib.dispatch import _dispatch
from pyforge import model as M
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
    
    error = ErrorController()
    static = StaticController()
    search = SearchController()
    projects = ProjectsController()

    def __init__(self):
        # Lookup user
        uid = session.get('userid', None)
        c.user = M.User.m.get(_id=uid) or M.User.anonymous

    def _lookup(self, *args):
        return self.projects._lookup(*args)

    @expose('pyforge.templates.index')
    @with_trailing_slash
    def index(self):
        """Handle the front-page."""
        return dict(roots=M.Project.m.find(dict(is_root=True)).all(),
                    users=M.User.m.find().all())

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)
        
    @expose('pyforge.templates.login')
    @without_trailing_slash
    def login(self, *args, **kwargs):
        return dict()

    @expose()
    def logout(self):
        session['userid'] = None
        session.save()
        redirect('/')

    @expose()
    def do_login(self, username, password):
        user = M.User.m.get(username=username)
        if user is None:
            session['userid'] = None
            session.save()
            raise exc.HTTPUnauthorized()
        if not user.validate_password(password):
            session['userid'] = None
            session.save()
            raise exc.HTTPUnauthorized()
        session['userid'] = user._id
        session.save()
        flash('Welcome back, %s' % user.display_name)
        redirect('/')

