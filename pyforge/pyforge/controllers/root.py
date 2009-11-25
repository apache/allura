# -*- coding: utf-8 -*-
"""Main Controller"""
import logging

from tg import expose, flash, redirect, session
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c
from webob import exc

from pyforge.lib.base import BaseController
from pyforge.lib.security import require_forge_access, require_authenticated
from pyforge.controllers.error import ErrorController

from pyforge.lib.dispatch import _dispatch
from pyforge import model as M
from .search import SearchController
from .static import StaticController


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

    def __init__(self):
        # Lookup user
        uid = session.get('userid', None)
        c.user = M.User.m.get(_id=uid) or M.User.anonymous

    @expose('pyforge.templates.index')
    @with_trailing_slash
    def index(self):
        """Handle the front-page."""
        return dict(roots=M.Project.m.find(dict(is_root=True)).all())

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)
        
    def _lookup(self, pname, *remainder):
        project = M.Project.m.get(_id=pname + '/')
        if project is None:
            raise exc.HTTPNotFound, pname
        c.project = project
        return ProjectController(), remainder

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

    @expose()
    def register_project(self, pid):
        require_authenticated()
        p = M.Project.make(dict(
                _id=pid + '/', name=pid,
                database='project:%s' % pid,
                is_root=True))
        c.project = p
        p.allow_user(c.user, 'create', 'read', 'delete', 'plugin', 'security')
        p.install_app('admin', 'admin')
        try:
            p.m.insert()
        except Exception, ex:
            flash('%s: %s' % (ex.__class__, str(ex)), 'error')
            redirect('/')
        redirect(pid + '/admin/')

class ProjectController(object):

    def _lookup(self, name, *remainder):
        subproject = M.Project.m.get(_id=c.project._id + name + '/')
        if subproject:
            c.project = subproject
            c.app = None
            return ProjectController(), remainder
        app = c.project.app_instance(name)
        if app is None:
            raise exc.HTTPNotFound, name
        c.app = app
        return app.root, remainder

    @expose('pyforge.templates.project_index')
    @with_trailing_slash
    def index(self):
        require_forge_access(c.project, 'read')
        return dict()

