# -*- coding: utf-8 -*-
"""Main Controller"""
import logging
import pkg_resources

from tg import expose, flash, require, url, request, redirect, session
from pylons.i18n import ugettext as _, lazy_ugettext as l_
from pylons import c
from webob import exc

from pyforge.lib.base import BaseController
from pyforge.lib.security import require_forge_access, require_project_access
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

    def __init__(self):
        # Lookup user
        uid = session.get('userid', None)
        if uid:
            c.user = M.User.m.get(_id=uid)
        else:
            c.user = None

    @expose('pyforge.templates.index')
    def index(self):
        """Handle the front-page."""
        return dict(roots=M.Project.m.find(dict(is_root=True)).all())

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)
        
    def _lookup(self, pname, *remainder):
        return ProjectController(pname + '/'), remainder

    @expose('pyforge.templates.login')
    def login(self):
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

class ProjectController(object):

    def __init__(self, name):
        self.project = p = M.Project.m.get(_id=name)
        self.app = ProjectAppsController(p)
        self.admin = ProjectAdminController(p)
        c.project = p

    def _lookup(self, subproject, *remainder):
        return ProjectController(self.project._id + subproject + '/'), remainder

    @expose('pyforge.templates.project_index')
    def index(self):
        require_forge_access(self.project, 'read')
        apps = M.AppConfig.m.find(dict(project_id=self.project._id)).all()
        installed_names = set(a.name for a in apps)
        available_apps = [
            (ep.name, ep.load()) for ep in pkg_resources.iter_entry_points('pyforge')
            if ep.name not in installed_names ]
        return dict(available_apps=available_apps,
                    apps=apps)

    @expose()
    def configure(self, _id=None, **kw):
        require_forge_access(self.project, 'plugin')
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
        require_forge_access(self.project, 'plugin')
        self.project.install_app(ep_name)
        redirect('.')

    @expose()
    def new_subproject(self, sp_name):
        require_forge_access(self.project, 'create')
        sp = self.project.new_subproject(sp_name)
        redirect('.')

    @expose()
    def delete_project(self):
        require_forge_access(self.project, 'delete')
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

class ProjectAdminController(object):

    def __init__(self, project):
        self.project = project
        self.app = ProjectAppAdminController(project)

    @expose('pyforge.templates.project_admin_index')
    def index(self):
        return dict(roles=M.ProjectRole.m.find().sort('_id').all(),
                    users=[M.User.m.get(_id=id) for id in self.project.acl.read ],
                    project=self.project)

    @expose()
    def add_group_role(self, name):
        r = M.ProjectRole.make(dict(_id=name))
        r.m.save()
        redirect('.')

    @expose()
    def add_user_role(self, id):
        u = M.User.m.get(_id=ObjectId.url_decode(id))
        name = u.username or u.display_name or u._id
        r = M.ProjectRole.make(dict(_id='*user-%s' % name, user_id=u._id))
        r.m.save()
        redirect('.')

    @expose()
    def add_role(self, role, subrole):
        role = M.ProjectRole.m.get(_id=role)
        role.roles.append(subrole)
        role.m.save()
        redirect('.')

    @expose()
    def del_role(self, role, subrole=None):
        role = M.ProjectRole.m.get(_id=role)
        if subrole:
            role.roles.remove(subrole)
            role.m.save()
        else:
            role.m.delete()
        redirect('.')

    @expose()
    def add_perm(self, permission, username):
        u = M.User.m.get(username=username)
        if not u:
            flash('No such user: %s', username)
            redirect('.')
        c.project.acl[permission].append(u._id)
        c.project.m.save()
        redirect('.')

    @expose()
    def del_perm(self, permission, user):
        c.project.acl[permission].remove(ObjectId.url_decode(user))
        c.project.m.save()
        redirect('.')

class ProjectAppAdminController(object):

    def __init__(self, project):
        self.project = project

    def _lookup(self, app_name, *remainder):
        app = self.project.app_instance(app_name)
        if app is None:
            raise exc.HTTPNotFound, app_name
        c.app = app
        return app.admin, remainder

