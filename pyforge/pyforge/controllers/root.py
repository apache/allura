# -*- coding: utf-8 -*-
"""Main Controller"""
import logging
import pkg_resources

from tg import expose, flash, require, url, request, redirect
from pylons.i18n import ugettext as _, lazy_ugettext as l_

from pylons import c

from pyforge.lib.base import BaseController
from pyforge.controllers.error import ErrorController

from pymongo.bson import ObjectId

from pyforge.lib.dispatch import _dispatch
from pyforge import model as M


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

    @expose('pyforge.templates.index')
    def index(self):
        """Handle the front-page."""
        return dict(roots=M.Project.m.find(dict(is_root=True)).all())

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)
        
    def _lookup(self, pname, *remainder):
        return ProjectController(pname + '/'), remainder

class ProjectController(object):

    def __init__(self, name):
        self.project = p = M.Project.m.get(_id=name)
        self.app = ProjectAppsController(p)
        c.project = p

    @expose('pyforge.templates.project_index')
    def index(self):
        return dict(apps=M.AppConfig.m.find(dict(project_id=self.project._id)))

    @expose()
    def configure(self, _id=None, **kw):
        app = M.AppConfig.m.get(_id=ObjectId.url_decode(_id))
        for k,v in kw.iteritems():
            app.config[k] = v
        app.m.save()
        redirect('.')

    def _lookup(self, subproject, *remainder):
        return ProjectController(self.project._id + subproject + '/'), remainder

class ProjectAppsController(object):

    def __init__(self, project):
        self.project = project

    def _lookup(self, app_name, *remainder):
        '''This should be replaced with something that looks up the pluggable
        app, configures it, and returns its root controller.'''
        for ep in pkg_resources.iter_entry_points('pyforge', app_name):
            App = ep.load()
            app = App(self.project.app_config(app_name).get('config'))
            return app.root, remainder
        return None

class DummyProjectAppController(object):
    'Dummy Pluggable Application Controller'

    def __init__(self, project_name, app_name):
        self.project_name = project_name
        self.app_name = app_name

    @expose()
    def index(self):
        return 'ProjectAppController(%s, %s)' % (repr(self.project_name), repr(self.app_name))
