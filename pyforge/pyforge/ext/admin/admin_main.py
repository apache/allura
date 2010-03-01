import difflib
from pprint import pformat
from collections import defaultdict
from mimetypes import guess_type

import pkg_resources
from pylons import c, request
from tg import expose, redirect, flash
from webob import exc
from pymongo.bson import ObjectId


from pyforge.app import Application, WidgetController, DefaultAdminController, SitemapEntry
from pyforge.lib.dispatch import _dispatch
from pyforge.lib.helpers import vardec
from pyforge import version
from pyforge import model as M
from pyforge.lib.security import require, has_project_access
from pyforge.model import nonce

class AdminWidgets(WidgetController):
    widgets=['users', 'plugin_status']

    def __init__(self, app): pass

    @expose('pyforge.ext.admin.templates.widgets.users')
    def users(self):
        return dict(project_roles=c.project.roles)

    @expose('pyforge.ext.admin.templates.widgets.plugin_status')
    def plugin_status(self):
        'Display # of ArtifactLinks for each (mounted) plugin'
        links = defaultdict(list)
        for ac in c.project.app_configs:
            mp = ac.options.mount_point
            q = M.ArtifactLink.query.find(dict(project_id=c.project._id,
                                               mount_point=mp))
            ct = q.count()
            if 0 < ct < 10:
                links[mp] = q.all()
            elif ct:
                links[mp] = [ None ] * ct
        return dict(links=links)

class AdminApp(Application):
    '''This is the admin app.  It is pretty much required for
    a functioning pyforge project.
    '''
    __version__ = version.__version__
    widget=AdminWidgets
    installable=False

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = ProjectAdminController()
        self.admin = AdminAppAdminController(self)
        self.sitemap = [ SitemapEntry('Admin', '.')[
                SitemapEntry('Plugins', '#plugin-admin'),
                SitemapEntry('ACLs', '#acl-admin'),
                SitemapEntry('Roles', '#role-admin'),
                ]]
        self.templates = pkg_resources.resource_filename('pyforge.ext.admin', 'templates')

    def sidebar_menu(self):
        return [
            SitemapEntry('Admin %s' % ac.options.mount_point,
                         ac.options.mount_point + '/').bind_app(self)
            for ac in c.project.app_configs
            ]

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
        plugins = [
            (ep.name, ep.load())
            for ep in pkg_resources.iter_entry_points('pyforge') ]
        installable_plugin_names = [ 
            name for (name, app) in plugins
            if app.installable ]
        return dict(
            installable_plugin_names=installable_plugin_names,
            roles=M.ProjectRole.query.find().sort('_id').all(),
            users=[M.User.query.get(_id=id) for id in c.project.acl.read ])

    def _dispatch(self, state, remainder):
        return _dispatch(self, state, remainder)
        
    def _lookup(self, name, *remainder):
        app = c.project.app_instance(name)
        if app is None:
            raise exc.HTTPNotFound, name
        return app.admin, remainder

    @expose()
    def update(self, name=None, short_description=None, description=None, icon=None, screenshot=None, **kw):
        c.project.name = name
        c.project.short_description = short_description
        c.project.description = description
        if icon is not None and icon != '':
            filename = icon.filename
            content_type = guess_type(filename)
            if content_type: content_type = content_type[0]
            else: content_type = 'application/octet-stream'
            if c.project.icon:
                M.ProjectFile.query.remove({'metadata.project_id':c.project._id, 'metadata.category':'icon'})
            with M.ProjectFile.create(
                content_type=content_type,
                filename=filename,
                category='icon',
                project_id=c.project._id) as fp:
                while True:
                    s = icon.file.read()
                    if not s: break
                    fp.write(s)
        if screenshot is not None and screenshot != '':
            filename = screenshot.filename
            content_type = guess_type(filename)
            if content_type: content_type = content_type[0]
            else: content_type = 'application/octet-stream'
            with M.ProjectFile.create(
                content_type=content_type,
                filename=filename,
                category='screenshot',
                project_id=c.project._id) as fp:
                while True:
                    s = screenshot.file.read()
                    if not s: break
                    fp.write(s)
        redirect('.')

    @expose()
    def join_neighborhood(self, nid):
        if not nid:
            n = M.Neighborhood.query.get(name='Projects')
            c.project.neighborhood_id = n._id
            flash('Joined %s' % n.name)
            redirect(c.project.url() + 'admin/')
        nid = ObjectId(str(nid))
        if nid not in c.project.neighborhood_invitations:
            flash('No invitation to that neighborhood', 'error')
            redirect('.')
        c.project.neighborhood_id = nid
        n = M.Neighborhood.query.get(_id=nid)
        flash('Joined %s' % n.name)
        redirect(c.project.url() + 'admin/')

    @vardec
    @expose()
    def update_mounts(self, subproject=None, plugin=None, new=None, **kw):
        if subproject is None: subproject = []
        if plugin is None: plugin = []
        for sp in subproject:
            if sp.get('delete'):
                M.Project.query.get(shortname=sp['shortname']).delete()
        for p in plugin:
            if p.get('delete'):
                c.project.uninstall_app(p['mount_point'])
        if new.get('install'):
            if new['ep_name'] == '':
                require(has_project_access('create'))
                sp = c.project.new_subproject(new['mount_point'] or nonce())
            else:
                require(has_project_access('plugin'))
                c.project.install_app(new['ep_name'], new['mount_point'] or new['ep_name'])
        redirect('.#mount-admin')

    @vardec
    @expose()
    def update_acl(self, permission=None, role=None, new=None, **kw):
        require(has_project_access('security'))
        if role is None: role = []
        for r in role:
            if r.get('delete'):
                c.project.acl[permission].remove(ObjectId(str(r['id'])))
        if new.get('add'):
            if new['id']:
                c.project.acl[permission].append(ObjectId(str(new['id'])))
            else:
                user = M.User.query.get(username=new['username'])
                if user is None:
                    flash('No user %s' % new['username'], 'error')
                    redirect('.')
                role = user.project_role()
                c.project.acl[permission].append(role._id)
        redirect('.#acl-admin')

    @vardec
    @expose()
    def update_roles(self, role=None, new=None, **kw):
        require(has_project_access('security'))
        if role is None: role = []
        for r in role:
            if r.get('delete'):
                role = M.ProjectRole.query.get(_id=ObjectId(str(r['id'])))
                if not role.special:
                    role.delete()
            if r['new'].get('add'):
                role = M.ProjectRole.query.get(_id=ObjectId(str(r['id'])))
                role.roles.append(ObjectId(str(r['new']['id'])))
            for sr in r.get('subroles', []):
                if sr.get('delete'):
                    role = M.ProjectRole.query.get(_id=ObjectId(str(r['id'])))
                    role.roles.remove(ObjectId(str(sr['id'])))
        if new.get('add'):
            M.ProjectRole(name=new['name'])
        redirect('.#role-admin')
            
class AdminAppAdminController(DefaultAdminController):
    '''Administer the admin app'''
    pass

    
