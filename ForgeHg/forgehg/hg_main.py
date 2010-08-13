#-*- python -*-
import logging
import re
import os
import sys
import shutil
import email
from subprocess import Popen
from datetime import datetime
from itertools import islice, chain
from urllib import urlencode, quote, unquote

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, response, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
import pylons
from pylons import g, c, request
from formencode import validators
from pymongo import bson
from webob import exc
from mercurial import ui, hg

from ming.orm.ormsession import ThreadLocalORMSession
from ming.orm.base import mapper
from pymongo.bson import ObjectId

# Pyforge-specific imports
from allura.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from allura.lib import helpers as h
from allura.lib.search import search
from allura.lib.decorators import audit, react
from allura.lib.security import require, has_artifact_access, has_project_access
from allura.model import Project, ProjectRole, User, ArtifactReference, Feed
from allura.controllers import BaseController

# Local imports
from forgehg import model
from forgehg import version
from .widgets import HgRevisionWidget
from .reactors import reactors
from .controllers import BranchBrowser, CommitBrowser

log = logging.getLogger(__name__)

class W(object):
    revision_widget = HgRevisionWidget()

class ForgeHgApp(Application):
    '''This is the Hg app for PyForge'''
    __version__ = version.__version__
    installable=False
    permissions = [ 'read', 'write', 'create', 'admin', 'configure' ]
    config_options = Application.config_options + [
        ConfigOption('cloned_from_project_id', ObjectId, None),
        ConfigOption('cloned_from_repo_id', ObjectId, None)
        ]
    tool_label='Hg'
    default_mount_label='Hg'
    default_mount_point='hg'
    ordinal=3

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = HgAdminController(self)

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

    def sidebar_menu(self):
        links = [ SitemapEntry('Home',c.app.url, ui_icon='home') ]
        if has_artifact_access('admin', app=c.app)():
            links.append(SitemapEntry('Admin', c.project.url()+'admin/'+self.config.options.mount_point, ui_icon='wrench'))
        repo = c.app.repo
        if repo and repo.status == 'ready':
            branches= repo.branchmap().keys()
            tags = repo.repo_tags().keys()
            if branches:
                links.append(SitemapEntry('Branches'))
                for b in branches:
                    links.append(SitemapEntry(
                            b, c.app.url + '?' + urlencode(dict(branch=b)),
                            className='nav_child'))
            if tags:
                links.append(SitemapEntry('Tags'))
                for b in tags:
                    links.append(SitemapEntry(
                            b, c.app.url + '?' + urlencode(dict(tag=b)),
                            className='nav_child'))
        return links

    @property
    def repo(self):
        return model.HgRepository.query.get(app_config_id=self.config._id)

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgehg', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project.name
        super(ForgeHgApp, self).install(project)
        # Setup permissions
        role_developer = ProjectRole.query.get(name='Developer')._id
        role_auth = ProjectRole.query.get(name='*authenticated')._id
        self.config.acl.update(
            configure=c.project.acl['tool'],
            read=c.project.acl['read'],
            write=[role_developer],
            create=[role_developer],
            admin=c.project.acl['tool'])
        repo = model.HgRepository(
            name=self.config.options.mount_point,
            tool='hg',
            status='initing')
        ThreadLocalORMSession.flush_all()
        cloned_from_project_id = self.config.options.get('cloned_from_project_id')
        cloned_from_repo_id = self.config.options.get('cloned_from_repo_id')
        if cloned_from_project_id is not None:
            with h.push_config(c, project=Project.query.get(_id=cloned_from_project_id)):
                cloned_from = model.HgRepository.query.get(_id=cloned_from_repo_id)
            g.publish('audit', 'scm.hg.clone',
                      dict(repo_name=repo.name, repo_path=repo.fs_path, cloned_from=cloned_from.full_fs_path))
        else:
            g.publish('audit', 'scm.hg.init',
                      dict(repo_name=repo.name, repo_path=repo.fs_path))


    def uninstall(self, project):
        g.publish('audit', 'scm.hg.uninstall', dict(project_id=project._id))

    @audit('scm.hg.uninstall')
    def _uninstall(self, routing_key, data):
        "Remove all the tool's artifacts and the physical repository"
        repo = self.repo
        if repo is not None:
            shutil.rmtree(repo.full_fs_path, ignore_errors=True)
        model.HgRepository.query.remove(dict(app_config_id=self.config._id))
        super(ForgeHgApp, self).uninstall(project_id=data['project_id'])


class HgAdminController(DefaultAdminController):

    def __init__(self, app):
        self.app = app
        self.repo = app.repo

    @with_trailing_slash
    def index(self, **kw):
        redirect('permissions')

    @without_trailing_slash
    @expose('forgehg.templates.admin_extensions')
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

    @expose('forgehg.templates.index')
    def index(self, offset=0, limit=10, branch=None, tag=None, **kw):
        offset=int(offset)
        repo = c.app.repo
        if repo and repo.status == 'ready':
            revisions = repo.log(branch=branch, tag=tag, offset=offset, limit=limit)
            args = dict(offset=offset+10)
            if branch: args['branch'] = branch
            if tag: args['tag'] = tag
            next_link = '?' + urlencode(args)
        else:
            revisions = []
            next_link=None
        c.revision_widget=W.revision_widget
        revisions = [ dict(value=r) for r in revisions ]
        for r in revisions:
            r.update(r['value'].context())
        return dict(repo=c.app.repo,
                    branch=branch,
                    tag=tag,
                    revisions=revisions,
                    next_link=next_link,
                    offset=offset,
                    allow_fork=True)

    @with_trailing_slash
    @expose('forgehg.templates.fork')
    def fork(self, to_name=None):
        from_repo = c.app.repo
        to_project_name = 'u/' + c.user.username
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        from_project = c.project
        to_project = Project.query.get(shortname=to_project_name)
        with h.push_config(c, project=to_project):
            require(has_project_access('tool', to_project))
            if request.method!='POST' or to_name is None:
                prefix_len = len(to_project_name+'/')
                in_use = [sp.shortname[prefix_len:] for sp in to_project.direct_subprojects]
                in_use += [ac.options['mount_point'] for ac in to_project.app_configs]
                return dict(from_repo=from_repo,
                            to_project_name=to_project_name,
                            in_use=in_use,
                            to_name=to_name or '')
            else:
                try:
                    to_project.install_app(
                        'Hg', to_name,
                        cloned_from_project_id=from_project._id,
                        cloned_from_repo_id=from_repo._id)
                    redirect('/'+to_project_name+'/'+to_name+'/')
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

h.mixin_reactors(ForgeHgApp, reactors)
