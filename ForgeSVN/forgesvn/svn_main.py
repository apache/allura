#-*- python -*-
import logging
import re
import sys
import shutil
from datetime import datetime
from itertools import islice
from urllib import urlencode

sys.path.append('/usr/lib/python2.6/dist-packages')

# Non-stdlib imports
import pkg_resources
import pysvn
from tg import expose, validate, redirect, response, config
from tg.decorators import with_trailing_slash, without_trailing_slash
import pylons
from pylons import g, c, request
from formencode import validators
from pymongo import bson
from webob import exc

from ming.orm.base import mapper
from ming.utils import LazyProperty
from pymongo.bson import ObjectId

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib.helpers import push_config, DateTimeConverter, mixin_reactors
from pyforge.lib.search import search
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole, User, ArtifactReference, Feed

# Local imports
from forgesvn import model
from forgesvn import version
from .widgets import SVNRevisionWidget
from .reactors import reactors

log = logging.getLogger(__name__)

class W(object):
    revision_widget = SVNRevisionWidget()

class ForgeSVNApp(Application):
    '''This is the SVN app for PyForge'''
    __version__ = version.__version__
    permissions = [ 'read', 'write', 'create', 'admin', 'configure' ]

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = SVNAdminController(self)

    @property
    def sitemap(self):
        menu_id = self.config.options.mount_point.title()
        with push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def admin_menu(self):
        return super(ForgeSVNApp, self).admin_menu()

    def sidebar_menu(self):
        links = [ SitemapEntry('Home',c.app.url, ui_icon='home') ]
        if has_artifact_access('admin', app=c.app)():
            links.append(SitemapEntry('Admin', c.project.url()+'admin/'+self.config.options.mount_point, ui_icon='wrench'))
        return links

    @property
    def repo(self):
        return model.SVNRepository.query.get(app_config_id=self.config._id)

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgesvn', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project.name
        super(ForgeSVNApp, self).install(project)
        # Setup permissions
        role_developer = ProjectRole.query.get(name='Developer')._id
        role_auth = ProjectRole.query.get(name='*authenticated')._id
        self.config.acl.update(
            configure=c.project.acl['tool'],
            read=c.project.acl['read'],
            create=[role_developer],
            write=[role_developer],
            admin=c.project.acl['tool'])
        repo = model.SVNRepository(
            name=self.config.options.mount_point,
            tool = 'svn',
            status = 'creating')
        g.publish('audit', 'scm.svn.init', dict(repo_name=repo.name, repo_path=repo.fs_path))

    def uninstall(self, project):
        g.publish('audit', 'scm.svn.uninstall', dict(project_id=project._id))

    @audit('scm.svn.uninstall')
    def _uninstall(self, routing_key, data):
        "Remove all the tool's artifacts and the physical repository"
        repo = self.repo
        if repo is not None:
            shutil.rmtree(repo.full_fs_path, ignore_errors=True)
        model.SVNRepository.query.remove(dict(app_config_id=self.config._id))
        super(ForgeSVNApp, self).uninstall(project_id=data['project_id'])


class SVNAdminController(DefaultAdminController):

    @with_trailing_slash
    def index(self):
        redirect('permissions')


class RootController(object):

    @expose('forgesvn.templates.index')
    def index(self, offset=0):
        offset=int(offset)
        repo = c.app.repo
        host = config.get('scm.host', request.host)
        if repo and repo.status=='ready':
            revisions = islice(repo.log(), offset, offset+10)
        else:
            revisions = []
        c.revision_widget=W.revision_widget
        next_link='?' + urlencode(dict(offset=offset+10))
        return dict(
            repo=c.app.repo,
            host=host,
            revisions=revisions,
            next_link=next_link)

    @expose()
    def _lookup(self, rev, *remainder):
        return CommitController(rev), remainder

class CommitController(object):

    def __init__(self, rev):
        self._rev = int(rev)

    @LazyProperty
    def revision(self):
        return c.app.repo.revision(self._rev)

    @expose('forgesvn.templates.commit')
    def index(self):
        c.revision_widget=W.revision_widget
        return dict(prev=self._rev-1,
                    next=self._rev+1,
                    revision=self.revision)

mixin_reactors(ForgeSVNApp, reactors)
