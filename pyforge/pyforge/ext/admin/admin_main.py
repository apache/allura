import difflib
from pprint import pformat

import pkg_resources
from pylons import c, request
from tg import expose, redirect, flash
from webob import exc
from pymongo.bson import ObjectId


from pyforge.app import Application, DefaultAdminController, SitemapEntry
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
        self.admin = AdminAppAdminController(self)
        self.sitemap = [ SitemapEntry('Admin', '.')[
                SitemapEntry('Plugins', '#plugin-admin'),
                SitemapEntry('ACLs', '#acl-admin'),
                SitemapEntry('Roles', '#role-admin'),
                ]]

    def sidebar_menu(self):
        return [
            SitemapEntry('Admin %s' % ac.options.mount_point,
                         ac.options.mount_point + '/').bind_app(self)
            for ac in c.project.app_configs
            ]

    @property
    def templates(self):
        return pkg_resources.resource_filename('pyforge.ext.admin', 'templates')

    def install(self, project):
        pass

    def uninstall(self, project):
        raise NotImplementedError, "uninstall"

class ProjectAdminController(object):

    def _check_security(self):
        require(has_project_access('read'),
                'Read access required')

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
        return app.admin, remainder

    @expose()
    def install(self, ep_name, mount_point):
        'install a plugin a the given mount point'
        require(has_project_access('plugin'))
        c.project.install_app(ep_name, mount_point)
        redirect('.#plugin-admin')

    @expose()
    def new_subproject(self, sp_name):
        'add a subproject for the current project'
        require(has_project_access('create'))
        sp = c.project.new_subproject(sp_name)
        redirect('.#project-admin')

    @expose()
    def delete_project(self):
        'delete the current project'
        require(has_project_access('delete'), 'Must have delete access')
        c.project.delete()
        redirect('..')

    @expose()
    def add_group_role(self, name):
        'add a named role to the project'
        require(has_project_access('security'))
        r = M.ProjectRole.make(dict(name=name))
        r.m.save()
        redirect('.#role-admin')

    @expose()
    def del_role(self, role):
        'Delete a role'
        require(has_project_access('security'))
        role = M.ProjectRole.m.get(_id=ObjectId.url_decode(role))
        if not role.special:
            role.m.delete()
        redirect('.#role-admin')

    @expose()
    def add_subrole(self, role, subrole):
        'Add a subrole to a role'
        require(has_project_access('security'))
        role = M.ProjectRole.m.get(_id=ObjectId.url_decode(role))
        role.roles.append(ObjectId.url_decode(subrole))
        role.m.save()
        redirect('.#role-admin')

    @expose()
    def add_role_to_user(self, role, username):
        'Add a subrole to a role'
        require(has_project_access('security'))
        user = M.User.m.get(username=username)
        pr = user.project_role()
        pr.roles.append(ObjectId.url_decode(role))
        pr.m.save()
        redirect('.#role-admin')

    @expose()
    def del_subrole(self, role, subrole):
        'Remove a subrole from a role'
        require(has_project_access('security'))
        role = M.ProjectRole.m.get(_id=ObjectId.url_decode(role))
        role.roles.remove(ObjectId.url_decode(subrole))
        role.m.save()
        redirect('.#role-admin')

    @expose()
    def add_perm(self, permission, role):
        require(has_project_access('security'))
        c.project.acl[permission].append(ObjectId.url_decode(role))
        c.project.m.save()
        redirect('.#acl-admin')

    @expose()
    def add_user_perm(self, permission, username):
        require(has_project_access('security'))
        user = M.User.m.get(username=username)
        if user is None:
            flash('No user %s' % username, 'error')
            redirect('.')
        role = user.project_role()
        c.project.acl[permission].append(role._id)
        c.project.m.save()
        redirect('.#acl-admin')

    @expose()
    def del_perm(self, permission, role):
        require(has_project_access('security'))
        c.project.acl[permission].remove(ObjectId.url_decode(role))
        c.project.m.save()
        redirect('.#acl-admin')

class AdminAppAdminController(DefaultAdminController):
    '''Administer the admin app'''
    pass

    
