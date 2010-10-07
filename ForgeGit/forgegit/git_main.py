#-*- python -*-
import logging
import re
import os
import sys
import shutil
from subprocess import Popen
from itertools import islice
from datetime import datetime
from urllib import quote, unquote

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, response, url, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
import pylons
from pylons import g, c, request
from formencode import validators
from pymongo import bson
from webob import exc

from ming.orm.ormsession import ThreadLocalORMSession
from ming.orm.base import mapper
from pymongo.bson import ObjectId

# Pyforge-specific imports
from allura.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from allura.lib import helpers as h
from allura.lib.search import search
from allura.lib.decorators import audit, react
from allura.lib.security import require, has_artifact_access, has_project_access, require_authenticated
from allura.model import Project, ProjectRole, User, ArtifactReference, Feed
from allura.controllers import BaseController

# Local imports
from forgegit import model
from forgegit import version
from .widgets import GitRevisionWidget
from .reactors import reactors
from .controllers import BranchBrowser, CommitBrowser

log = logging.getLogger(__name__)

class W(object):
    revision_widget = GitRevisionWidget()

class ForgeGitApp(Application):
    '''This is the Git app for PyForge'''
    __version__ = version.__version__
    permissions = [ 'read', 'write', 'create', 'admin', 'configure' ]
    config_options = Application.config_options + [
        ConfigOption('cloned_from_project_id', ObjectId, None),
        ConfigOption('cloned_from_repo_id', ObjectId, None)
        ]
    tool_label='Git'
    default_mount_label='Git'
    default_mount_point='git'
    ordinal=2

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = GitAdminController(self)

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
        if self.repo.status != 'ready':
            return [
                SitemapEntry('Repository is %s' % self.repo.status) ]
        links = [ SitemapEntry('Browse',c.app.url + url(quote('ref/master:/')), ui_icon='folder-collapsed'),
                  SitemapEntry('History', c.app.url + url(quote('ref/master:/')) + 'log',
                               ui_icon='document-b', small=c.app.repo.count())]
        if has_artifact_access('admin', app=c.app)():
            links.append(SitemapEntry('Admin', c.project.url()+'admin/'+self.config.options.mount_point, ui_icon='tool-admin'))
        repo = c.app.repo
        if repo:
            branches= [ b.name for b in repo.branches ]
            tags = [ t.name for t in repo.repo_tags ]
            if branches:
                links.append(SitemapEntry('Branches'))
                for b in branches:
                    links.append(SitemapEntry(
                            b, url(c.app.url, dict(branch=b)),
                            className='nav_child',
                            small=c.app.repo.count(branch=b)))
            if tags:
                links.append(SitemapEntry('Tags'))
                for b in tags:
                    links.append(SitemapEntry(
                            b, url(c.app.url, dict(branch=b)),
                            className='nav_child'))
        return links

    @property
    def repo(self):
        return model.GitRepository.query.get(app_config_id=self.config._id)

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgegit', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project.name
        super(ForgeGitApp, self).install(project)
        # Setup permissions
        role_developer = ProjectRole.query.get(name='Developer')._id
        role_auth = ProjectRole.query.get(name='*authenticated')._id
        self.config.acl.update(
            configure=c.project.acl['tool'],
            read=c.project.acl['read'],
            create=[role_developer],
            write=[role_developer],
            admin=c.project.acl['tool'])
        repo = model.GitRepository(
            name=self.config.options.mount_point + '.git',
            tool='git',
            status='initing')
        ThreadLocalORMSession.flush_all()
        cloned_from_project_id = self.config.options.get('cloned_from_project_id')
        cloned_from_repo_id = self.config.options.get('cloned_from_repo_id')
        if cloned_from_project_id is not None:
            with h.push_config(c, project=Project.query.get(_id=cloned_from_project_id)):
                cloned_from = model.GitRepository.query.get(_id=cloned_from_repo_id)
            g.publish('audit', 'scm.git.clone',
                      dict(repo_name=repo.name, repo_path=repo.fs_path, cloned_from=cloned_from.full_fs_path))
        else:
            g.publish('audit', 'scm.git.init',
                      dict(repo_name=repo.name, repo_path=repo.fs_path))


    def uninstall(self, project):
        g.publish('audit', 'scm.git.uninstall', dict(project_id=project._id))

    @audit('scm.git.uninstall')
    def _uninstall(self, routing_key, data):
        "Remove all the tool's artifacts and the physical repository"
        repo = self.repo
        if repo is not None:
            shutil.rmtree(repo.full_fs_path, ignore_errors=True)
        model.GitRepository.query.remove(dict(app_config_id=self.config._id))
        super(ForgeGitApp, self).uninstall(project_id=data['project_id'])


class GitAdminController(DefaultAdminController):

    def __init__(self, app):
        self.app = app
        self.repo = app.repo

    @with_trailing_slash
    def index(self, **kw):
        redirect('permissions')

    @without_trailing_slash
    @expose('jinja:git/admin_extensions.html')
    def extensions(self, **kw):
        return dict(app=self.app,
                    allow_config=has_artifact_access('configure', app=self.app)(),
                    additional_viewable_extensions=getattr(self.repo, 'additional_viewable_extensions', ''))

    @without_trailing_slash
    @expose()
    def set_extensions(self, **post_data):
        self.repo.additional_viewable_extensions = post_data['additional_viewable_extensions']


class RootController(BaseController):

    def _check_security(self):
        require(has_artifact_access('read'))

    def __init__(self):
        self.ref = Refs()
        self.ci = Commits()

    @expose()
    def refresh(self):
        g.publish('react', 'scm.git.refresh_commit')
        return '%r refresh queued.\n' % c.app.repo

    @expose('jinja:git/index.html')
    def index(self, offset=0, branch='master', **kw):
        # Add the colon so we know where the branch part ends
        redirect(url(quote('ref/%s:/' % branch)))

    @with_trailing_slash
    @expose('jinja:git/fork.html')
    def fork(self, to_name=None):
        require_authenticated()
        from_repo = c.app.repo
        to_project_name = 'u/' + c.user.username
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        from_project = c.project
        to_project = Project.query.get(shortname=to_project_name)
        with h.push_config(c, project=to_project):
            if request.method!='POST' or to_name is None:
                prefix_len = len(to_project_name+'/')
                in_use = [sp.shortname[prefix_len:] for sp in to_project.direct_subprojects]
                in_use += [ac.options['mount_point'] for ac in to_project.app_configs]
                return dict(from_repo=from_repo,
                            to_project_name=to_project_name,
                            in_use=in_use,
                            to_name=to_name or '')
            else:
                if not to_project.database_configured:
                    to_project.configure_project_database(is_user_project=True)
                require(has_project_access('tool', to_project))
                try:
                    to_project.install_app(
                        'Git', to_name,
                        cloned_from_project_id=from_project._id,
                        cloned_from_repo_id=from_repo._id)
                    redirect('/'+to_project_name+'/'+to_name+'/')
                except exc.HTTPRedirection:
                    raise
                except Exception, ex:
                    flash(str(ex), 'error')
                    redirect(request.referer)

class Refs(object):

    @expose()
    def _lookup(self, *parts):
        parts = map(unquote, parts)
        ref = []
        while parts:
            part = parts.pop(0)
            ref.append(part)
            if part.endswith(':'): break
        ref = '/'.join(ref)[:-1]
        return BranchBrowser(ref), parts

class Commits(object):

    @expose()
    def _lookup(self, ci, *remainder):
        return CommitBrowser(ci), remainder

h.mixin_reactors(ForgeGitApp, reactors)
