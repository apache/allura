# -*- coding: utf-8 -*-
"""Main Controller"""

from tg import expose, flash, require, url, request, redirect
from pylons.i18n import ugettext as _, lazy_ugettext as l_

from pyforge.lib.base import BaseController
from pyforge.controllers.error import ErrorController

from pyforge.lib.dispatch import _dispatch, default

__all__ = ['RootController']

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

    @expose('pyforge.templates.index')
    def index(self):
        """Handle the front-page."""
        return dict(page='index')

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)
        
    def _lookup(self, pname, *remainder):
        return ProjectController(pname), remainder

class ProjectController(object):

    def __init__(self, name):
        self.name = name
        self.app = ProjectAppsController(self.name)

    @expose()
    def index(self):
        return 'ProjectController for %s' % self.name

    def _lookup(self, subproject, *remainder):
        return ProjectController(self.name + '/' + subproject), remainder

class ProjectAppsController(object):

    def __init__(self, project_name):
        self.project_name = project_name

    @property
    def project(self):
        return M.Project.m.get(name=self.project_name)

    def _lookup(self, app_name, *remainder):
        '''This should be replaced with something that looks up the pluggable
        app, configures it, and returns its root controller.'''
        # plugin = load_plugin(app_name, self.project.config)
        # root = plugin.root
        root = DummyProjectAppController(self.project_name, app_name)
        return root, remainder

class DummyProjectAppController(object):
    'Dummy Pluggable Application Controller'

    def __init__(self, project_name, app_name):
        self.project_name = project_name
        self.app_name = app_name

    @expose()
    def index(self):
        return 'ProjectAppController(%s, %s)' % (repr(self.project_name), repr(self.app_name))
