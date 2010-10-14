import logging
import shutil
from urllib import quote

from pylons import c, g
from tg import expose, redirect, url
from tg.decorators import with_trailing_slash, without_trailing_slash
from pymongo.bson import ObjectId

from allura import version
from allura.lib import helpers as h
from allura import model as M
from allura.lib import security
from allura.lib.decorators import audit
from allura.app import Application, SitemapEntry, DefaultAdminController, ConfigOption

log = logging.getLogger(__name__)


class RepositoryApp(Application):
    END_OF_REF_ESCAPE='~'
    __version__ = version.__version__
    permissions = [ 'read', 'write', 'create', 'admin', 'configure' ]
    config_options = Application.config_options + [
        ConfigOption('cloned_from_project_id', ObjectId, None),
        ConfigOption('cloned_from_repo_id', ObjectId, None)
        ]
    tool_label='Repository'
    default_mount_label='Source'
    default_mount_point='src'
    ordinal=2
    forkable=False
    default_branch_name=None # master or default or some such
    repo=None # override with a property in child class

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.admin = RepoAdminController(self)

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = [SitemapEntry('Viewable Files', admin_url + 'extensions', className='nav_child')]
        # if self.permissions and has_artifact_access('configure', app=self)():
        #     links.append(SitemapEntry('Permissions', admin_url + 'permissions', className='nav_child'))
        return links

    @h.exceptionless([], log)
    def sidebar_menu(self):
        if not self.repo or self.repo.status != 'ready':
            return [
                SitemapEntry(self.repo.status) ]
        if self.default_branch_name:
            default_branch_url = (
                c.app.url
                + url(quote(self.default_branch_name + self.END_OF_REF_ESCAPE))
                + '/')
        else:
            default_branch_url = c.app.url
        links = [
            SitemapEntry('Browse', default_branch_url,ui_icon='folder-collapsed') ]
        if c.app.repo.heads:
            links.append(
                SitemapEntry(
                    'History', default_branch_url+'log/',
                    ui_icon='document-b', small=c.app.repo.heads[0].count))
        if self.forkable and self.repo.status == 'ready':
            links.append(SitemapEntry('Fork', c.app.url + 'fork', ui_icon='fork'))
        if security.has_artifact_access('admin', app=c.app)():
            links.append(SitemapEntry('Admin',
                                      c.project.url()+'admin/'+self.config.options.mount_point,
                                      ui_icon='tool-admin'))
        if self.repo.upstream_repo.name:
            links += [
                SitemapEntry('Clone of'),
                SitemapEntry(self.repo.upstream_repo.name, self.repo.upstream_repo.url,
                             className='nav_child'),
                SitemapEntry('Request Merge', c.app.url + 'merge_request',
                             ui_icon='merge',
                             className='nav_child')
                ]
        if self.repo.branches:
            links.append(SitemapEntry('Branches'))
            for b in self.repo.branches:
                links.append(SitemapEntry(
                        b.name, url(c.app.url, dict(branch='ref/' + b.name)),
                        className='nav_child',
                        small=b.count))
        if self.repo.repo_tags:
            links.append(SitemapEntry('Tags'))
            for b in self.repo.repo_tags:
                links.append(SitemapEntry(
                        b.name, url(c.app.url, dict(branch='ref/' + b.name)),
                        className='nav_child',
                        small=b.count))
        return links

    def install(self, project):
        self.config.options['project_name'] = project.name
        super(RepositoryApp, self).install(project)
        role_developer = M.ProjectRole.query.get(name='Developer')._id
        self.config.acl.update(
            configure=c.project.acl['tool'],
            read=c.project.acl['read'],
            create=[role_developer],
            write=[role_developer],
            admin=c.project.acl['tool'])

    def uninstall(self, project):
        g.publish('audit', 'repo.uninstall', dict(project_id=project._id))

    @classmethod
    @audit('repo.init')
    def _init(cls, routing_key, data):
        c.app.repo.init()
        M.Notification.post_user(
            c.user, c.app.repo, 'created',
            text='Repository %s/%s created' % (
                c.project.shortname, c.app.config.options.mount_point))

    @classmethod
    @audit('repo.clone')
    def _clone(cls, routing_key, data):
        if not c.app.forkable:
            return cls._init(cls, routing_key, data)
        c.app.repo.init_as_clone(
            data['cloned_from_path'],
            data['cloned_from_name'],
            data['cloned_from_url'])
        M.Notification.post_user(
            c.user, c.app.repo, 'created',
            text='Repository %s/%s created' % (
                c.project.short_name, c.app.config.options.mount_point))

    @classmethod
    @audit('repo.refresh')
    def _refresh(cls, routing_key, data):
        c.app.repo.refresh()

    @classmethod
    @audit('repo.uninstall')
    def _uninstall(cls, routing_key, data):
        "Remove all the tool's artifacts and the physical repository"
        repo = c.app.repo
        if repo is not None:
            shutil.rmtree(repo.full_fs_path, ignore_errors=True)
            repo.delete()
        super(RepositoryApp, c.app).uninstall(project=c.project)

class RepoAdminController(DefaultAdminController):

    def __init__(self, app):
        self.app = app
        self.repo = app.repo

    def _check_security(self):
        security.require(security.has_artifact_access('configure', app=self.app))

    @with_trailing_slash
    @expose()
    def index(self, **kw):
        redirect('extensions')

    @without_trailing_slash
    @expose('jinja:repo/admin_extensions.html')
    def extensions(self, **kw):
        return dict(app=self.app,
                    allow_config=True,
                    additional_viewable_extensions=getattr(self.repo, 'additional_viewable_extensions', ''))

    @without_trailing_slash
    @expose()
    def set_extensions(self, **post_data):
        self.repo.additional_viewable_extensions = post_data['additional_viewable_extensions']
