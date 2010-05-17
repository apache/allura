import difflib
from pprint import pformat
from collections import defaultdict
from mimetypes import guess_type
import Image

import pkg_resources
from pylons import c, request
from tg import expose, redirect, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from webob import exc
from pymongo.bson import ObjectId


from pyforge.app import Application, WidgetController, DefaultAdminController, SitemapEntry
from pyforge.lib.security import has_artifact_access
from pyforge.lib import helpers as h
from pyforge import version
from pyforge import model as M
from pyforge.lib.security import require, has_project_access
from pyforge.lib.widgets import form_fields as ffw

class W:
    markdown_editor = ffw.MarkdownEdit()
    label_edit = ffw.LabelEdit()

class AdminWidgets(WidgetController):
    widgets=['users', 'tool_status']

    def __init__(self, app): pass

    @expose('pyforge.ext.admin.templates.widgets.users')
    def users(self):
        def uniq(users): 
            t = {}
            for user in users:
                t[user.username] = user
            return t.values()
        # remove duplicates, ticket #195
        project_users = uniq([r.user for r in c.project.roles])
        return dict(project_users=project_users)

    @expose('pyforge.ext.admin.templates.widgets.tool_status')
    def tool_status(self):
        'Display # of ArtifactLinks for each (mounted) tool'
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
        self.templates = pkg_resources.resource_filename('pyforge.ext.admin', 'templates')
        self.sitemap = [ SitemapEntry('Admin','.')]

    def sidebar_menu(self):
        admin_url = c.project.url()+'admin/'
        links = [SitemapEntry('Project'),
                 SitemapEntry('Overview', admin_url+'overview', className='nav_child'),
                 SitemapEntry('Tools/Subprojects', admin_url+'tools', className='nav_child')]
        if len(c.project.neighborhood_invitations):
            links.append(SitemapEntry('Invitation(s)', admin_url+'invitations', className='nav_child'))
        if has_project_access('security')():
            links.append(SitemapEntry('Permissions', admin_url+'perms', className='nav_child'))
        # if has_project_access('security')():
        #     links.append(SitemapEntry('Permissions', admin_url+'permissions', className='nav_child'))
        # if c.project.is_root and has_project_access('security')():
        #     links.append(SitemapEntry('Roles', admin_url+'roles', className='nav_child'))

        for ac in c.project.app_configs:
            app = c.project.app_instance(ac.options.mount_point)
            if len(app.config_options) > 1 or (app.permissions and has_artifact_access('configure', app=app)()) and len(app.admin_menu()):
                links.append(SitemapEntry(ac.options.mount_point).bind_app(self))
                links = links + app.admin_menu()
        return links

    def admin_menu(self):
        return []

    def install(self, project):
        pass

    def uninstall(self, project):
        raise NotImplementedError, "uninstall"

class ProjectAdminController(object):

    def _check_security(self):
        require(has_project_access('read'),
                'Read access required')

    @with_trailing_slash
    @expose()
    def index(self):
        redirect('overview')

    @without_trailing_slash
    @expose('pyforge.ext.admin.templates.project_invitations')
    def invitations(self):
        return dict()

    @without_trailing_slash
    @expose('pyforge.ext.admin.templates.project_overview')
    def overview(self):
        c.markdown_editor = W.markdown_editor
        c.label_edit = W.label_edit
        return dict(categories=M.ProjectCategory.query.find(dict(parent_id=None)).sort('label').all())

    @without_trailing_slash
    @expose('pyforge.ext.admin.templates.project_tools')
    def tools(self):
        tools = [
            (ep.name, ep.load())
            for ep in pkg_resources.iter_entry_points('pyforge') ]
        installable_tool_names = [
            name for (name, app) in tools
            if app.installable ]
        c.markdown_editor = W.markdown_editor
        c.label_edit = W.label_edit
        psort = [(n, M.Project.query.find(dict(is_root=True, neighborhood_id=n._id)).sort('shortname').all())
                 for n in M.Neighborhood.query.find().sort('name')]
        return dict(
            projects=psort,
            installable_tool_names=installable_tool_names,
            roles=M.ProjectRole.query.find().sort('_id').all(),
            categories=M.ProjectCategory.query.find(dict(parent_id=None)).sort('label').all(),
            users=[M.User.query.get(_id=id) for id in c.project.acl.read ])

    @without_trailing_slash
    @expose('pyforge.ext.admin.templates.project_perms')
    def perms(self):
        """Simplfied permission management screen for the project"""
        c.user_select = ffw.ProjectUserSelect()
        return dict()

    @without_trailing_slash
    @expose('pyforge.ext.admin.templates.project_permissions')
    def permissions(self):
        """Advanced permission management screen for the project. Currently not linked to anywhere."""
        return dict()

    @without_trailing_slash
    @expose('pyforge.ext.admin.templates.project_roles')
    def roles(self):
        return dict(roles=M.ProjectRole.query.find().sort('_id').all())

    @expose()
    def _lookup(self, name, *remainder):
        app = c.project.app_instance(name)
        if app is None:
            raise exc.HTTPNotFound, name
        return app.admin, remainder

    @expose()
    def update(self, name=None, short_description=None, description=None, icon=None, screenshot=None, category=None, **kw):
        if 'delete_icon' in kw:
            M.ProjectFile.query.remove({'metadata.project_id':c.project._id, 'metadata.category':'icon'})
            redirect('.')
        elif 'delete' in kw:
            c.project.deleted = True
            for sp in c.project.subprojects:
                sp.deleted = True
            redirect('.')
        elif 'undelete' in kw:
            c.project.deleted = False
            for sp in c.project.subprojects:
                sp.deleted = False
            redirect('.')
        c.project.name = name
        c.project.short_description = short_description
        c.project.description = description
        if category:
            c.project.category_id = ObjectId(category)
        else:
            c.project.category_id = None
        if 'labels' in kw:
            c.project.labels = kw['labels'].split(',')
            del kw['labels']
        if icon is not None and icon != '':
            if h.supported_by_PIL(icon.type):
                filename = icon.filename
                if icon.type: content_type = icon.type
                else: content_type = 'application/octet-stream'
                image = Image.open(icon.file)
                format = image.format
                image = h.square_image(image)
                image.thumbnail((48, 48), Image.ANTIALIAS)
                if c.project.icon:
                    M.ProjectFile.query.remove({'metadata.project_id':c.project._id, 'metadata.category':'icon'})
                with M.ProjectFile.create(
                    content_type=content_type,
                    filename=filename,
                    category='icon',
                    project_id=c.project._id) as fp:
                    image.save(fp, format)
            else:
                flash('The icon must be jpg, png, or gif format.')
        if screenshot is not None and screenshot != '':
            if h.supported_by_PIL(screenshot.type):
                filename = screenshot.filename
                if screenshot.type: content_type = screenshot.type
                else: content_type = 'application/octet-stream'
                image = Image.open(screenshot.file)
                format = image.format
                with M.ProjectFile.create(
                    content_type=content_type,
                    filename=filename,
                    category='screenshot',
                    project_id=c.project._id) as fp:
                    fp_name = fp.name
                    image.save(fp, format)
                image = h.square_image(image)
                image.thumbnail((150, 150), Image.ANTIALIAS)
                with M.ProjectFile.create(
                    content_type=content_type,
                    filename=fp_name,
                    category='screenshot_thumb',
                    project_id=c.project._id) as fp:
                    image.save(fp, format)
            else:
                flash('Screenshots must be jpg, png, or gif format.')
        redirect('overview')

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
        redirect('invitations')

    @h.vardec
    @expose()
    def update_mounts(self, subproject=None, tool=None, new=None, **kw):
        if subproject is None: subproject = []
        if tool is None: tool = []
        for sp in subproject:
            if sp.get('delete'):
                M.Project.query.get(shortname=sp['shortname']).delete()
        for p in tool:
            if p.get('delete'):
                c.project.uninstall_app(p['mount_point'])
        if new and new.get('install'):
            ep_name = new['ep_name']
            if not ep_name:
                require(has_project_access('create'))
                mount_point = new['mount_point'] or h.nonce()
                if not h.re_path_portion.match(mount_point):
                    flash('Invalid mount point', 'error')
                    redirect(request.referer)
                sp = c.project.new_subproject(mount_point)
            else:
                require(has_project_access('tool'))
                mount_point = new['mount_point'] or ep_name.lower()
                if not h.re_path_portion.match(mount_point):
                    flash('Invalid mount point for %s' % ep_name, 'error')
                    redirect(request.referer)
                c.project.install_app(ep_name, mount_point)
        redirect('tools')

    @h.vardec
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
        redirect('permissions')

    @h.vardec
    @expose()
    def update_roles(self, role=None, new=None, **kw):
        require(has_project_access('security'))
        if role is None: role = []
        for r in role:
            if r.get('delete'):
                role = M.ProjectRole.query.get(_id=ObjectId(str(r['id'])))
                if not role.special:
                    role.delete()
            if r.get('new', {}).get('add'):
                role = M.ProjectRole.query.get(_id=ObjectId(str(r['id'])))
                role.roles.append(ObjectId(str(r['new']['id'])))
            for sr in r.get('subroles', []):
                if sr.get('delete'):
                    role = M.ProjectRole.query.get(_id=ObjectId(str(r['id'])))
                    role.roles.remove(ObjectId(str(sr['id'])))
        if new.get('add'):
            M.ProjectRole(name=new['name'])
        redirect('roles')

    @h.vardec
    @expose()
    def update_user_roles(self, role=None, new=None, **kw):
        require(has_project_access('security'))
        if role is None: role = []
        for r in role:
            if r.get('new', {}).get('add'):
                user = M.User.query.find({'username':str(r['new']['id'])}).first()
                if user:
                    ur = user.project_role()
                    if ObjectId(str(r['id'])) not in ur.roles:
                        ur.roles.append(ObjectId(str(r['id'])))
            for u in r.get('users', []):
                if u.get('delete'):
                    ur = M.ProjectRole.query.get(user_id=ObjectId(str(u['id'])))
                    ur.roles.remove(ObjectId(str(r['id'])))
        redirect('perms')

class AdminAppAdminController(DefaultAdminController):
    '''Administer the admin app'''
    pass

