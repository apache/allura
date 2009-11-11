# -*- coding: utf-8 -*-
"""Main Controller"""
import logging
import pkg_resources

from tg import expose, flash, require, url, request, redirect
from pylons.i18n import ugettext as _, lazy_ugettext as l_
from pylons import c
from webob import exc

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

    def _lookup(self, subproject, *remainder):
        return ProjectController(self.project._id + subproject + '/'), remainder

    @expose('pyforge.templates.project_index')
    def index(self):
        apps = M.AppConfig.m.find(dict(project_id=self.project._id)).all()
        installed_names = set(a.name for a in apps)
        available_apps = [
            (ep.name, ep.load()) for ep in pkg_resources.iter_entry_points('pyforge')
            if ep.name not in installed_names ]
        return dict(available_apps=available_apps,
                    apps=apps)

    @expose()
    def configure(self, _id=None, **kw):
        app_config = M.AppConfig.m.get(_id=ObjectId.url_decode(_id))
        if kw.pop('delete', False):
            self.project.uninstall_app(app_config.name)
            redirect('.')
        for k,v in kw.iteritems():
            app_config.config[k] = v
        app_config.m.save()
        redirect('.')

    @expose()
    def install(self, ep_name):
        self.project.install_app(ep_name)
        redirect('.')

    @expose()
    def new_subproject(self, sp_name):
        sp = self.project.new_subproject(sp_name)
        redirect('.')

    @expose()
    def delete_project(self):
        self.project.delete()
        redirect('..')

class ProjectAppsController(object):

    def __init__(self, project):
        self.project = project

    def _lookup(self, app_name, *remainder):
        app = self.project.app_instance(app_name)
        if app is None:
            raise exc.HTTPNotFound, app_name
        c.app = app
        return app.root, remainder

class DummyProjectAppController(object):
    'Dummy Pluggable Application Controller'

    def __init__(self, project_name, app_name):
        self.project_name = project_name
        self.app_name = app_name

    @expose()
    def index(self):
        return 'ProjectAppController(%s, %s)' % (repr(self.project_name), repr(self.app_name))
