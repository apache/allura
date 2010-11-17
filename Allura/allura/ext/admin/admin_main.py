import difflib
import logging
from pprint import pformat
from collections import defaultdict
from mimetypes import guess_type
import Image

import pkg_resources
from pylons import c, g, request
from tg import expose, redirect, flash, validate
from tg.decorators import with_trailing_slash, without_trailing_slash
from webob import exc
from bson import ObjectId
from formencode.validators import UnicodeString


from allura.app import Application, WidgetController, DefaultAdminController, SitemapEntry
from allura.lib.security import has_artifact_access
from allura.lib import helpers as h
from allura import version
from allura import model as M
from allura.lib.security import require, has_project_access
from allura.lib.widgets import form_fields as ffw
from allura.lib import exceptions as forge_exc
from allura.lib import plugin
from allura.controllers import BaseController

log = logging.getLogger(__name__)

class W:
    markdown_editor = ffw.MarkdownEdit()
    label_edit = ffw.LabelEdit()

class AdminWidgets(WidgetController):
    widgets=['users', 'tool_status']

    def __init__(self, app): pass

    @expose('jinja:widgets/users.html')
    def users(self):
        def uniq(users): 
            t = {}
            for user in users:
                t[user.username] = user
            return t.values()
        # remove duplicates, ticket #195
        project_users = uniq([r.user for r in c.project.roles if r.user])
        return dict(project_users=project_users)

    @expose('jinja:widgets/tool_status.html')
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
    a functioning allura project.
    '''
    __version__ = version.__version__
    widget=AdminWidgets
    installable=False
    _installable_tools = None

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = ProjectAdminController()
        self.admin = AdminAppAdminController(self)
        self.templates = pkg_resources.resource_filename('allura.ext.admin', 'templates')
        self.sitemap = [ SitemapEntry('Admin','.')]

    def is_visible_to(self, user):
        '''Whether the user can view the app.'''
        return has_project_access('create')(user=user)

    @staticmethod
    def installable_tools_for(project):
        cls = AdminApp
        if cls._installable_tools is None:
            tools = sorted(
                [ dict(name=ep.name, app=ep.load())
                  for ep in pkg_resources.iter_entry_points('allura') ],
                key=lambda t:(t['app'].status_int(), t['app'].ordinal))
            cls._installable_tools = [ t for t in tools if t['app'].installable ]
        return [ t for t in cls._installable_tools
            if t['app'].status in project.allowed_tool_status ]

    @h.exceptionless([], log)
    def sidebar_menu(self):
        links = []
        if c.project.shortname == '--init--':
            admin_url = c.project.neighborhood.url()+'_admin/'
            links = links + [
                     SitemapEntry('Overview', admin_url+'overview', className='nav_child'),
                     SitemapEntry('Permissions', admin_url+'permissions', className='nav_child'),
                     SitemapEntry('Awards', admin_url+'accolades', className='nav_child')]
        admin_url = c.project.url()+'admin/'
        if len(links):
            links.append(SitemapEntry('Project'))
        links = links + [SitemapEntry('Overview', admin_url+'overview', className='nav_child'),
                         SitemapEntry('Tools', admin_url+'tools', className='nav_child')]
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
#             if len(app.config_options) > 3 or (app.permissions and
#             has_artifact_access('configure', app=app)()) and
#             len(app.admin_menu()):
            if app.permissions and has_artifact_access('configure', app=app)() and len(app.admin_menu()):
                links.append(SitemapEntry(ac.options.mount_point).bind_app(self))
                links = links + app.admin_menu()
        return links

    def admin_menu(self):
        return []

    def install(self, project):
        pass

    def uninstall(self, project):
        raise NotImplementedError, "uninstall"

class ProjectAdminController(BaseController):

    def _check_security(self):
        require(has_project_access('read'),
                'Read access required')

    @with_trailing_slash
    @expose()
    def index(self, **kw):
        redirect('overview')

    @without_trailing_slash
    @expose('jinja:project_invitations.html')
    def invitations(self):
        return dict()

    @without_trailing_slash
    @expose('jinja:project_overview.html')
    def overview(self, **kw):
        c.markdown_editor = W.markdown_editor
        c.label_edit = W.label_edit
        categories = M.ProjectCategory.query.find(dict(parent_id=None)).sort('label').all()
        return dict(categories=categories)

    @without_trailing_slash
    @expose('jinja:project_tools_starter.html')
    def tools_starter(self, **kw):
        return dict()

    @without_trailing_slash
    @expose('jinja:project_tools.html')
    def tools(self, **kw):
        c.markdown_editor = W.markdown_editor
        c.label_edit = W.label_edit
        mounts = []
        for sub in c.project.direct_subprojects:
            mounts.append({'ordinal':sub.ordinal,'sub':sub})
        for ac in c.project.app_configs:
            if ac.tool_name != 'search':
                ordinal = 'ordinal' in ac.options and ac.options['ordinal'] or 0
                mounts.append({'ordinal':ordinal,'ac':ac})
        mounts = sorted(mounts, key=lambda e: e['ordinal'])
        return dict(
            mounts=mounts,
            installable_tools=AdminApp.installable_tools_for(c.project),
            roles=M.ProjectRole.query.find(dict(project_id=c.project.root_project._id)).sort('_id').all(),
            categories=M.ProjectCategory.query.find(dict(parent_id=None)).sort('label').all(),
            users=[M.User.query.get(_id=id) for id in c.project.acl.read ])

    @without_trailing_slash
    @expose('jinja:project_perms.html')
    def perms(self, **kw):
        """Simplified permission management screen for the project"""
        c.user_select = ffw.ProjectUserSelect()
        return dict()

    @without_trailing_slash
    @expose('jinja:project_permissions.html')
    def permissions(self):
        """Advanced permission management screen for the project. Currently not linked to anywhere."""
        return dict()

    @without_trailing_slash
    @expose('jinja:project_roles.html')
    def roles(self):
        return dict(roles=M.ProjectRole.query.find(dict(project_id=c.project.root_project._id)).sort('_id').all())

    @expose()
    def _lookup(self, name, *remainder):
        app = c.project.app_instance(name)
        if app is None:
            raise exc.HTTPNotFound, name
        return app.admin, remainder

    @expose()
    @validate(validators=dict(
            name=UnicodeString(),
            short_description=UnicodeString(),
            description=UnicodeString()))
    def update(self, name=None,
               short_description=None,
               description=None,
               icon=None,
               screenshot=None,
               category=None,
               **kw):
        require(has_project_access('update'), 'Update access required')

        if 'delete_icon' in kw:
            M.ProjectFile.query.remove(dict(project_id=c.project._id, category='icon'))
            h.log_action(log, 'remove project icon').info('')
            redirect('.')
        elif 'delete' in kw:
            h.log_action(log, 'delete project').info('')
            plugin.ProjectRegistrationProvider.get().delete_project(c.project, c.user)
            redirect('.')
        elif 'undelete' in kw:
            h.log_action(log, 'undelete project').info('')
            plugin.ProjectRegistrationProvider.get().undelete_project(c.project, c.user)
            redirect('.')
        if name != c.project.name:
            h.log_action(log, 'change project name').info('')
            c.project.name = name
        if short_description != c.project.short_description:
            h.log_action(log, 'change project short description').info('')
            c.project.short_description = short_description
        if description != c.project.description:
            h.log_action(log, 'change project description').info('')
            c.project.description = description
        category = category and ObjectId(category) or None
        if category != c.project.category_id:
            h.log_action(log, 'change project category').info('')
            c.project.category_id = category
        labels = kw.pop('labels', None)
        if labels is not None:
            labels = labels.split(',')
            if labels != c.project.labels:
                h.log_action(log, 'update project labels').info('')
                c.project.labels = labels

        if icon is not None and icon != '':
            if c.project.icon:
                M.ProjectFile.remove(dict(project_id=c.project._id, category='icon'))
            M.ProjectFile.save_image(
                icon.filename, icon.file, content_type=icon.type,
                square=True, thumbnail_size=(48,48),
                thumbnail_meta=dict(project_id=c.project._id,category='icon'))
        if screenshot is not None and screenshot != '':
            M.ProjectFile.save_image(
                screenshot.filename, screenshot.file, content_type=screenshot.type,
                save_original=True,
                original_meta=dict(project_id=c.project._id,category='screenshot'),
                square=True, thumbnail_size=(150,150),
                thumbnail_meta=dict(project_id=c.project._id,category='screenshot_thumb'))
        g.publish('react', 'forge.project_updated')
        redirect('overview')

    @expose()
    def join_neighborhood(self, nid):
        require(has_project_access('update'), 'Update access required')
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
    def update_mount_order(self, subs=None, tools=None, **kw):
        if subs:
            for sp in subs:
                p = M.Project.query.get(shortname=sp['shortname'])
                p.ordinal = int(sp['ordinal'])
        if tools:
            for p in tools:    
                c.project.app_config(p['mount_point']).options.ordinal = int(p['ordinal'])
        redirect('tools')

    @h.vardec
    @expose()
    def update_mounts(self, subproject=None, tool=None, new=None, **kw):
        if subproject is None: subproject = []
        if tool is None: tool = []
        for sp in subproject:
            if sp.get('delete'):
                require(has_project_access('delete'), 'Delete access required')
                h.log_action(log, 'delete subproject').info(
                    'delete subproject %s', sp['shortname'],
                    meta=dict(name=sp['shortname']))
                p = M.Project.query.get(shortname=sp['shortname'])
                plugin.ProjectRegistrationProvider.get().delete_project(p, c.user)
            elif not new:
                p = M.Project.query.get(shortname=sp['shortname'])
                p.name = sp['name']
                p.ordinal = int(sp['ordinal'])
        for p in tool:
            if p.get('delete'):
                require(has_project_access('tool'), 'Delete access required')
                h.log_action(log, 'uninstall tool').info(
                    'uninstall tool %s', p['mount_point'],
                    meta=dict(mount_point=p['mount_point']))
                c.project.uninstall_app(p['mount_point'])
            elif not new:
                options = c.project.app_config(p['mount_point']).options
                options.mount_label = p['mount_label']
                options.ordinal = int(p['ordinal'])
        try:
            if new and new.get('install'):
                ep_name = new.get('ep_name', None)
                if not ep_name:
                    require(has_project_access('create'))
                    mount_point = new['mount_point'].lower() or h.nonce()
                    h.log_action(log, 'create subproject').info(
                        'create subproject %s', mount_point,
                        meta=dict(mount_point=mount_point,name=new['mount_label']))
                    sp = c.project.new_subproject(mount_point)
                    sp.name = new['mount_label']
                    sp.ordinal = int(new['ordinal'])
                else:
                    require(has_project_access('tool'))
                    mount_point = new['mount_point'].lower() or ep_name.lower()
                    h.log_action(log, 'install tool').info(
                        'install tool %s', mount_point,
                        meta=dict(tool_type=ep_name, mount_point=mount_point, mount_label=new['mount_label']))
                    c.project.install_app(ep_name, mount_point, mount_label=new['mount_label'], ordinal=new['ordinal'])
        except forge_exc.ToolError, exc:
            flash('%s: %s' % (exc.__class__.__name__, exc.args[0]),
                  'error')
        redirect('tools')

    @h.vardec
    @expose()
    def starter_mounts(self, **kw):
        require(has_project_access('tool'))
        for i, tool in enumerate(kw):
            h.log_action(log, 'install tool').info(
                'install tool %s', tool,
                meta=dict(tool_type=tool, mount_point=(tool.lower() or h.nonce()), mount_label=tool))
            c.project.install_app(tool, (tool.lower() or h.nonce()), mount_label=tool, ordinal=i)
        redirect('overview')

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
                user = M.User.by_username(new['username'])
                if user is None:
                    flash('No user %s' % new['username'], 'error')
                    redirect('.')
                role = user.project_role()
                c.project.acl[permission].append(role._id)
        g.publish('react', 'forge.project_updated')
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
        if new and new.get('add'):
            M.ProjectRole.upsert(name=new['name'], project_id=c.project.root_project._id)
        g.publish('react', 'forge.project_updated')
        redirect('roles')

    @h.vardec
    @expose()
    def update_user_roles(self, role=None, new=None, **kw):
        require(has_project_access('security'))
        if role is None: role = []
        for r in role:
            if r.get('new', {}).get('add'):
                username = unicode(r['new']['id'])
                try:
                    user = M.User.by_username(username)
                except AssertionError:
                    user = None
                if user:
                    ur = user.project_role()
                    if ObjectId(str(r['id'])) not in ur.roles:
                        ur.roles.append(ObjectId(str(r['id'])))
                        h.log_action(log, 'add_user_to_role').info(
                            '%s to %s', user.username, r['id'],
                            meta=dict(user=user.username, role=r['id']))
                else:
                    flash('No user %s' % username, 'error')
            for u in r.get('users', []):
                if u.get('delete'):
                    user = M.User.query.get(_id=ObjectId(u['id']))
                    ur = M.ProjectRole.by_user(user)
                    ur.roles = [ rid for rid in ur.roles if str(rid) != r['id'] ]
                    h.log_action(log, 'remove_user_from_role').info(
                        '%s from %s', u['id'], r['id'],
                        meta=dict(user_role=u['id'], role=r['id']))
        g.publish('react', 'forge.project_updated')
        redirect('perms')

class AdminAppAdminController(DefaultAdminController):
    '''Administer the admin app'''
    pass

