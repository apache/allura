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
from pyforge.lib.security import require_forge_access

class AdminApp(Application):
    '''This is the admin app.  It is pretty much required for
    a functioning pyforge project.
    '''
    __version__ = version.__version__

    def __init__(self, config):
        self.root = ProjectAdminController()
        self.admin = AdminAppAdminController()
        Application.__init__(self, config)

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
        require_forge_access(c.project, 'plugin')
        c.project.install_app(ep_name, mount_point)
        redirect('.')

    @expose()
    def new_subproject(self, sp_name):
        require_forge_access(c.project, 'create')
        sp = c.project.new_subproject(sp_name)
        redirect('.')

    @expose()
    def delete_project(self):
        require_forge_access(c.project, 'delete')
        c.project.delete()
        redirect('..')

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

class AdminAppAdminController(DefaultAdminController):
    '''Administer the admin app'''
    pass

    
