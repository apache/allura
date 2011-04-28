import difflib
import logging
from pprint import pformat
from collections import defaultdict
import Image
from bson import ObjectId

import pkg_resources
from pylons import c, g, request
from tg import expose, redirect, flash, validate
from tg.decorators import with_trailing_slash, without_trailing_slash
from webob import exc
from bson import ObjectId
from formencode.validators import UnicodeString

from allura.app import Application, WidgetController, DefaultAdminController, SitemapEntry
from allura.lib import helpers as h
from allura import version
from allura import model as M
from allura.lib.security import has_access, require_access
from allura.lib.widgets import form_fields as ffw
from allura.lib import exceptions as forge_exc
from allura.lib import plugin
from allura.controllers import BaseController
from allura.lib.decorators import require_post

from . import widgets as aw
from allura.lib.widgets.project_list import ProjectScreenshots

log = logging.getLogger(__name__)

class W:
    markdown_editor = ffw.MarkdownEdit()
    label_edit = ffw.LabelEdit()
    mount_delete = ffw.Lightbox(name='mount_delete',trigger='a.mount_delete')
    admin_modal = ffw.Lightbox(name='admin_modal',trigger='a.admin_modal')
    install_modal = ffw.Lightbox(name='install_modal',trigger='a.install_trig')
    group_card = aw.GroupCard()
    permission_card = aw.PermissionCard()
    group_settings = aw.GroupSettings()
    new_group_settings = aw.NewGroupSettings()
    screenshot_admin = aw.ScreenshotAdmin()
    screenshot_list = ProjectScreenshots()

class AdminWidgets(WidgetController):
    widgets=['users', 'tool_status']

    def __init__(self, app): pass

    @expose('jinja:allura.ext.admin:templates/widgets/users.html')
    def users(self):
        return dict(project_users=c.project.users())

    @expose('jinja:allura.ext.admin:templates/widgets/tool_status.html')
    def tool_status(self):
        'Display # of Shortlinks for each (mounted) tool'
        links = defaultdict(list)
        for ac in c.project.app_configs:
            mp = ac.options.mount_point
            q = M.Shortlink.query.find(dict(
                project_id=c.project._id,
                app_config_id = ac._id))
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
    tool_label = 'admin'
    icons={
        24:'allura/images/admin_24.png',
        32:'allura/images/admin_32.png',
        48:'allura/images/admin_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = ProjectAdminController()
        self.admin = AdminAppAdminController(self)
        self.templates = pkg_resources.resource_filename('allura.ext.admin', 'templates')
        self.sitemap = [ SitemapEntry('Admin','.')]

    def is_visible_to(self, user):
        '''Whether the user can view the app.'''
        return has_access(c.project, 'create')(user=user)

    @staticmethod
    def installable_tools_for(project):
        cls = AdminApp
        if cls._installable_tools is None:
            tools = []
            for ep in pkg_resources.iter_entry_points('allura'):
                try:
                    tools.append(dict(name=ep.name, app=ep.load()))
                except ImportError:
                    log.warning('Canot load entry point %s', ep)
            tools.sort(key=lambda t:(t['app'].status_int(), t['app'].ordinal))
            cls._installable_tools = [ t for t in tools if t['app'].installable ]
        return [ t for t in cls._installable_tools
            if t['app'].status in project.allowed_tool_status ]

    @h.exceptionless([], log)
    def sidebar_menu(self):
        links = []
        if c.project.shortname == '--init--':
            admin_url = c.project.neighborhood.url()+'_admin/'
            links = links + [
                     SitemapEntry('Neighborhood'),
                     SitemapEntry('Overview', admin_url+'overview', className='nav_child'),
                     SitemapEntry('Awards', admin_url+'accolades', className='nav_child')]
        admin_url = c.project.url()+'admin/'
        if len(links):
            links.append(SitemapEntry('Project'))
        links += [
            SitemapEntry('Summary', admin_url+'overview', className='nav_child'),
            SitemapEntry('Homepage', admin_url+'homepage', className='nav_child'),
            SitemapEntry('Screenshots', admin_url+'screenshots', className='nav_child')
            ]
        if has_access(c.project, 'admin')():
            links.append(SitemapEntry('Permissions', admin_url+'permissions/', className='nav_child'))
        links.append(SitemapEntry('Tools', admin_url+'tools', className='nav_child'))
        if c.project.is_root and has_access(c.project, 'admin')():
            links.append(SitemapEntry('Usergroups', admin_url+'groups/', className='nav_child'))
        if len(c.project.neighborhood_invitations):
            links.append(SitemapEntry('Invitation(s)', admin_url+'invitations', className='nav_child'))
        return links

    def admin_menu(self):
        return []

    def install(self, project):
        pass

    def uninstall(self, project): # pragma no cover
        raise NotImplementedError, "uninstall"

class ProjectAdminController(BaseController):

    def _check_security(self):
        require_access(c.project, 'admin')

    def __init__(self):
        self.permissions = PermissionsController()
        self.groups = GroupsController()

    @with_trailing_slash
    @expose('jinja:allura.ext.admin:templates/project_admin.html')
    def index(self, **kw):
        return dict()

    @without_trailing_slash
    @expose('jinja:allura.ext.admin:templates/project_invitations.html')
    def invitations(self):
        return dict()

    @without_trailing_slash
    @expose('jinja:allura.ext.admin:templates/project_overview.html')
    def overview(self, **kw):
        c.markdown_editor = W.markdown_editor
        c.label_edit = W.label_edit
        categories = M.ProjectCategory.query.find(dict(parent_id=None)).sort('label').all()
        return dict(categories=categories)

    @without_trailing_slash
    @expose('jinja:allura.ext.admin:templates/project_homepage.html')
    def homepage(self, **kw):
        c.markdown_editor = W.markdown_editor
        return dict()

    @without_trailing_slash
    @expose('jinja:allura.ext.admin:templates/project_screenshots.html')
    def screenshots(self, **kw):
        c.screenshot_admin = W.screenshot_admin
        c.screenshot_list = W.screenshot_list
        return dict()

    @without_trailing_slash
    @expose('jinja:allura.ext.admin:templates/project_tools.html')
    def tools(self, **kw):
        c.markdown_editor = W.markdown_editor
        c.label_edit = W.label_edit
        c.mount_delete = W.mount_delete
        c.admin_modal = W.admin_modal
        c.install_modal = W.install_modal
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
            categories=M.ProjectCategory.query.find(dict(parent_id=None)).sort('label').all())

    @without_trailing_slash
    @expose()
    def clone(self,
              repo_type=None, source_url=None,
              mount_point=None, mount_label=None,
              **kw):
        require_access(c.project, 'admin')
        if repo_type is None:
            return (
                '<form method="get">'
                '<input name="repo_type" value="Git">'
                '<input name="source_url">'
                '<input type="submit">'
                '</form>')
        for ep in pkg_resources.iter_entry_points('allura', repo_type):
            break
        if ep is None or source_url is None:
            raise exc.HTTPNotFound
        h.log_action(log, 'install tool').info(
            'clone repo from %s', source_url,
            meta=dict(tool_type=repo_type, mount_point=mount_point, mount_label=mount_label))
        c.project.install_app(
            repo_type,
            mount_point=mount_point,
            mount_label=mount_label,
            init_from_url=source_url)
        redirect('tools')

    @without_trailing_slash
    @expose('jinja:allura.ext.admin:templates/project_permissions.html')
    def groups(self, **kw):
        return dict()

    @expose()
    def _lookup(self, name, *remainder):
        app = c.project.app_instance(name)
        if app is None:
            raise exc.HTTPNotFound, name
        return app.admin, remainder

    @expose()
    @require_post()
    @validate(validators=dict(
            name=UnicodeString(),
            short_description=UnicodeString()))
    def update(self, name=None,
               short_description=None,
               icon=None,
               category=None,
               **kw):
        require_access(c.project, 'update')

        if 'delete_icon' in kw:
            M.ProjectFile.query.remove(dict(project_id=c.project._id, category='icon'))
            h.log_action(log, 'remove project icon').info('')
            g.post_event('project_updated')
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
        g.post_event('project_updated')
        redirect('overview')

    @expose()
    @require_post()
    @validate(validators=dict(description=UnicodeString()))
    def update_homepage(self, description=None, homepage_title=None, **kw):
        require_access(c.project, 'update')
        if description != c.project.description:
            h.log_action(log, 'change project description').info('')
            c.project.description = description
        if homepage_title != c.project.homepage_title:
            h.log_action(log, 'change project homepage title').info('')
            c.project.homepage_title = homepage_title
        g.post_event('project_updated')
        redirect('homepage')

    @expose()
    @require_post()
    @validate(W.screenshot_admin)
    def add_screenshot(self, screenshot=None, caption=None, **kw):
        require_access(c.project, 'update')
        if len(c.project.get_screenshots()) >= 6:
            flash('You may not have more than 6 screenshots per project.','error')
        elif screenshot is not None and screenshot != '':
            M.ProjectFile.save_image(
                screenshot.filename, screenshot.file, content_type=screenshot.type,
                save_original=True,
                original_meta=dict(project_id=c.project._id,category='screenshot',caption=caption),
                square=True, thumbnail_size=(150,150),
                thumbnail_meta=dict(project_id=c.project._id,category='screenshot_thumb'))
            g.post_event('project_updated')
        redirect('screenshots')

    @expose()
    @require_post()
    def delete_screenshot(self, id=None, **kw):
        require_access(c.project, 'update')
        if id is not None and id != '':
            M.ProjectFile.query.remove(dict(project_id=c.project._id, _id=ObjectId(id)))
            g.post_event('project_updated')
        redirect('screenshots')

    @expose()
    @require_post()
    def edit_screenshot(self, id=None, caption=None, **kw):
        require_access(c.project, 'update')
        if id is not None and id != '':
            M.ProjectFile.query.get(project_id=c.project._id, _id=ObjectId(id)).caption=caption
            g.post_event('project_updated')
        redirect('screenshots')

    @expose()
    @require_post()
    def join_neighborhood(self, nid):
        require_access(c.project, 'admin')
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
    @require_post()
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
    @require_post()
    def update_mounts(self, subproject=None, tool=None, new=None, **kw):
        if subproject is None: subproject = []
        if tool is None: tool = []
        for sp in subproject:
            if sp.get('delete'):
                require_access(c.project, 'admin')
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
                require_access(c.project, 'admin')
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
                    require_access(c.project, 'create')
                    mount_point = new['mount_point'].lower() or h.nonce()
                    h.log_action(log, 'create subproject').info(
                        'create subproject %s', mount_point,
                        meta=dict(mount_point=mount_point,name=new['mount_label']))
                    sp = c.project.new_subproject(mount_point)
                    sp.name = new['mount_label']
                    sp.ordinal = int(new['ordinal'])
                else:
                    require_access(c.project, 'admin')
                    mount_point = new['mount_point'].lower() or ep_name.lower()
                    h.log_action(log, 'install tool').info(
                        'install tool %s', mount_point,
                        meta=dict(tool_type=ep_name, mount_point=mount_point, mount_label=new['mount_label']))
                    c.project.install_app(ep_name, mount_point, mount_label=new['mount_label'], ordinal=new['ordinal'])
        except forge_exc.ToolError, exc:
            flash('%s: %s' % (exc.__class__.__name__, exc.args[0]),
                  'error')
        g.post_event('project_updated')
        redirect('tools')

class PermissionsController(BaseController):

    def _check_security(self):
        require_access(c.project, 'admin')

    @with_trailing_slash
    @expose('jinja:allura.ext.admin:templates/project_permissions.html')
    def index(self, **kw):
        c.card = W.permission_card
        return dict(permissions=self._index_permissions())

    @without_trailing_slash
    @expose()
    @h.vardec
    @require_post()
    def update(self, card=None, **kw):
        permissions = self._index_permissions()
        for args in card:
            perm = args['id']
            permissions[perm] = []
            new_group_ids = args.get('new', [])
            group_ids = args.get('value', [])
            if isinstance(new_group_ids, basestring):
                new_group_ids = [ new_group_ids ]
            if isinstance(group_ids, basestring):
                group_ids = [ group_ids ]
            role_ids = map(ObjectId, group_ids + new_group_ids)
            permissions[perm] = role_ids
        c.project.acl = []
        for perm, role_ids in permissions.iteritems():
            c.project.acl += [
                M.ACE.allow(rid, perm) for rid in role_ids ]
        g.post_event('project_updated')
        redirect('.')

    def _index_permissions(self):
        permissions = dict(
            (p,[]) for p in c.project.permissions)
        for ace in c.project.acl:
            if ace.access == M.ACE.ALLOW:
                permissions[ace.permission].append(ace.role_id)
        return permissions

class GroupsController(BaseController):

    def _check_security(self):
        require_access(c.project, 'admin')

    @with_trailing_slash
    @expose('jinja:allura.ext.admin:templates/project_groups.html')
    def index(self, **kw):
        c.admin_modal = W.admin_modal
        c.card = W.group_card
        roles = c.project.named_roles
        roles.append(None)
        return dict(roles=roles)

    @without_trailing_slash
    @expose()
    @require_post()
    @h.vardec
    def update(self, card=None, **kw):
        for pr in card:
            group = M.ProjectRole.query.get(_id=ObjectId(pr['id']))
            assert group.project == c.project, 'Security violation'
            user_ids = pr.get('value', [])
            new_users = pr.get('new', [])
            if isinstance(user_ids, basestring):
                user_ids = [ user_ids ]
            if isinstance(new_users, basestring):
                new_users = [ new_users ]
            # Handle new users in groups
            for username in new_users:
                user = M.User.by_username(username)
                if not user:
                    flash('User %s not found' % pr['new'], 'error')
                    redirect('.')
                user.project_role().roles.append(group._id)
            # Handle users removed from groups
            user_ids = set(map(ObjectId, user_ids))
            for role in M.ProjectRole.query.find(
                dict(user_id={'$ne':None}, roles=group._id)):
                if role.user_id not in user_ids:
                    role.roles = [ rid for rid in role.roles if rid != group._id ]
        g.post_event('project_updated')
        redirect('.')

    @without_trailing_slash
    @expose('jinja:allura.ext.admin:templates/project_group.html')
    def new(self):
        c.form = W.new_group_settings
        return dict(
            group=None,
            show_settings=True,
            action="create")

    @expose()
    @require_post()
    @validate(W.new_group_settings)
    @h.vardec
    def create(self, name=None, **kw):
        if M.ProjectRole.by_name(name):
            flash('%s already exists' % name, 'error')
        else:
            M.ProjectRole(project_id=c.project._id, name=name)
        g.post_event('project_updated')
        redirect('.')

    @expose()
    def _lookup(self, name, *remainder):
        return GroupController(name), remainder

class GroupController(BaseController):

    def __init__(self, name):
        self._group = M.ProjectRole.query.get(_id=ObjectId(name))

    @with_trailing_slash
    @expose('jinja:allura.ext.admin:templates/project_group.html')
    def index(self):
        if self._group.name in ('Admin', 'Developer', 'Member'):
            show_settings = False
            action = None
        else:
            show_settings = True
            action = self._group.settings_href + 'update'
        c.form = W.group_settings
        return dict(
            group=self._group,
            show_settings=show_settings,
            action=action)

    @expose()
    @h.vardec
    @require_post()
    @validate(W.group_settings)
    def update(self, _id=None, delete=None, name=None, **kw):
        pr = M.ProjectRole.by_name(name)
        if pr and pr._id != _id._id:
            flash('%s already exists' % name, 'error')
            redirect('..')
        if delete:
            _id.delete()
            flash('%s deleted' % name)
            redirect('..')
        _id.name = name
        flash('%s updated' % name)
        redirect('..')

class AdminAppAdminController(DefaultAdminController):
    '''Administer the admin app'''
    pass

