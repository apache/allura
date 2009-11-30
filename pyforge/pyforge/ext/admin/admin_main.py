import difflib
from pprint import pformat

import pkg_resources
from pylons import c, request
from tg import expose, redirect, flash
from webob import exc
from pymongo.bson import ObjectId


from pyforge.app import Application, DefaultAdminController
from pyforge.lib.dispatch import _dispatch
from pyforge import version
from pyforge import model as M
from pyforge.lib.security import require, has_project_access

class AdminApp(Application):
    '''This is the admin app.  It is pretty much required for
    a functioning pyforge project.
    '''
    __version__ = version.__version__

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = ProjectAdminController()
        self.admin = AdminAppAdminController()

    @property
    def templates(self):
        return pkg_resources.resource_filename('pyforge.ext.admin', 'templates')

    def install(self, project):
        pass

    def uninstall(self, project):
        raise NotImplementedError, "uninstall"

class ProjectAdminController(object):

    @expose('pyforge.ext.admin.templates.admin_index')
    def index(self):
        plugin_names = [
            ep.name for ep in pkg_resources.iter_entry_points('pyforge') ]
        return dict(
            plugin_names=plugin_names,
            roles=M.ProjectRole.m.find().sort('_id').all(),
            users=[M.User.m.get(_id=id) for id in c.project.acl.read ])

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)
        
    def _lookup(self, name, *remainder):
        app = c.project.app_instance(name)
        if app is None:
            raise exc.HTTPNotFound, name
        c.app = app
        return app.admin, remainder

    @expose()
    def install(self, ep_name, mount_point):
        require(has_project_access('plugin'))
        c.project.install_app(ep_name, mount_point)
        redirect('.')

    @expose()
    def new_subproject(self, sp_name):
        require(has_project_access('create'))
        sp = c.project.new_subproject(sp_name)
        redirect('.')

    @expose()
    def delete_project(self):
        require(has_project_access('delete'))
        c.project.delete()
        redirect('..')

    @expose()
    def add_group_role(self, name):
        require(has_project_access('security'))
        r = M.ProjectRole.make(dict(_id=name))
        r.m.save()
        redirect('.')

    @expose()
    def add_user_role(self, id):
        require(has_project_access('security'))
        u = M.User.m.get(_id=ObjectId.url_decode(id))
        c.project.add_user_role(u)
        redirect('.')

    @expose()
    def add_role(self, role, subrole):
        require(has_project_access('security'))
        role = M.ProjectRole.m.get(_id=role)
        role.roles.append(subrole)
        role.m.save()
        redirect('.')

    @expose()
    def del_role(self, role, subrole=None):
        require(has_project_access('security'))
        role = M.ProjectRole.m.get(_id=role)
        if subrole:
            role.roles.remove(subrole)
            role.m.save()
        else:
            role.m.delete()
        redirect('.')

    @expose()
    def add_perm(self, permission, role):
        require(has_project_access('security'))
        c.project.acl[permission].append(role)
        c.project.m.save()
        redirect('.')

    @expose()
    def del_perm(self, permission, role):
        require(has_project_access('security'))
        c.project.acl[permission].remove(role)
        c.project.m.save()
        redirect('.')

class AdminAppAdminController(DefaultAdminController):
    '''Administer the admin app'''
    pass

    
