# -*- coding: utf-8 -*-
"""Main Controller"""
import logging

import pkg_resources
from pylons import c
from webob import exc
from tg import expose

from pyforge.lib.security import require, has_project_access
from pyforge.lib.base import BaseController
from pyforge.controllers.root import ProjectController
from pyforge.lib.dispatch import _dispatch
from pyforge import model as M

__all__ = ['RootController']

log = logging.getLogger(__name__)

class TestController(BaseController, ProjectController):
    '''Root controller for testing -- it behaves just like a
    ProjectController for test/ except that all plugins are mounted,
    on-demand, at the mount point that is the same as their entry point
    name.

    Also, the test_admin is perpetually logged in here.
    '''

    def __init__(self):
        c.project = M.Project.m.get(_id='test/')
        c.user = M.User.m.get(username='test_admin')

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)
        
    def _lookup(self, name, *remainder):
        subproject = M.Project.m.get(_id=c.project._id + name + '/')
        if subproject:
            c.project = subproject
            c.app = None
            return ProjectController(), remainder
        app = c.project.app_instance(name)
        if app is None:
            c.project.install_app(name, name)
            app = c.project.app_instance(name)
            if app is None:
                raise exc.HTTPNotFound, name
        c.app = app
        return app.root, remainder

    @expose('pyforge.templates.project_index')
    def index(self):
        require(has_project_access('read'))
        return dict()
