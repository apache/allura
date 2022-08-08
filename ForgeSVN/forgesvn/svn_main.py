#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import logging

import six
from tg import tmpl_context as c, request

# Non-stdlib imports
from ming.utils import LazyProperty
from ming.orm.ormsession import ThreadLocalORMSession
from tg import expose, redirect, validate, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from timermiddleware import Timer
from paste.deploy.converters import asint

# Pyforge-specific imports
import allura.tasks.repo_tasks
from allura.controllers import BaseController
from allura.controllers.repository import RepoRootController
from allura.controllers.repository import RepoRestController
from allura.lib.decorators import require_post
from allura.lib.repository import RepositoryApp, RepoAdminController
from allura.app import SitemapEntry, ConfigOption, AdminControllerMixin
from allura.lib import helpers as h
from allura.lib import validators as v
from allura import model as M

# Local imports
from . import model as SM
from . import version
from . import widgets
from .controllers import BranchBrowser
from .model.svn import svn_path_exists

log = logging.getLogger(__name__)


class ForgeSVNApp(RepositoryApp):

    '''This is the SVN app for PyForge'''
    __version__ = version.__version__
    config_options = RepositoryApp.config_options + [
        ConfigOption('checkout_url', str, '')
    ]
    permissions_desc = dict(RepositoryApp.permissions_desc, **{
        'write': 'Repo commit access.',
        'admin': 'Set permissions, checkout url, and viewable files. Import a remote repo.',
    })
    tool_label = 'SVN'
    tool_description = """
        Subversion ("svn") is a centralized version control system.  In general, SVN is simpler to use
        but not as powerful as distributed systems like Git and Mercurial.
    """
    ordinal = 4
    forkable = False
    default_branch_name = 'HEAD'

    def __init__(self, project, config):
        super().__init__(project, config)
        self.root = BranchBrowser()
        default_root = RepoRootController()
        self.api_root = RepoRestController()
        self.root.refresh = default_root.refresh
        self.root.commit_browser = default_root.commit_browser
        self.root.commit_browser_data = SVNCommitBrowserController().commit_browser_data
        self.root.status = default_root.status
        self.admin = SVNRepoAdminController(self)

    @LazyProperty
    def repo(self):
        return SM.Repository.query.get(app_config_id=self.config._id)

    def install(self, project):
        '''Create repo object for this tool'''
        super().install(project)
        SM.Repository(
            name=self.config.options.mount_point,
            tool='svn',
            status='initializing',
            fs_path=self.config.options.get('fs_path'))
        ThreadLocalORMSession.flush_all()
        init_from_url = self.config.options.get('init_from_url')
        init_from_path = self.config.options.get('init_from_path')
        if init_from_url or init_from_path:
            allura.tasks.repo_tasks.clone.post(
                cloned_from_path=init_from_path,
                cloned_from_name=None,
                cloned_from_url=init_from_url)
        else:
            allura.tasks.repo_tasks.init.post()

    def admin_menu(self):
        links = super().admin_menu()
        links.insert(1, SitemapEntry(
            'Import Repo',
            c.project.url() + 'admin/' + self.config.options.mount_point + '/' + 'importer/'))
        return links


class SVNRepoAdminController(RepoAdminController):

    def __init__(self, app):
        super().__init__(app)
        self.importer = SVNImportController(self.app)

    @without_trailing_slash
    @expose('jinja:forgesvn:templates/svn/checkout_url.html')
    def checkout_url(self, **kw):
        return dict(app=self.app, allow_config=True)

    @without_trailing_slash
    @expose()
    @require_post()
    @validate({'external_checkout_url': v.NonHttpUrl})
    def set_checkout_url(self, **post_data):
        checkout_url = (post_data.get('checkout_url') or '').strip()
        external_checkout_url = (post_data.get('external_checkout_url') or '').strip()
        if not checkout_url or svn_path_exists("file://%s%s/%s" %
                                               (self.app.repo.fs_path,
                                                self.app.repo.name,
                                                checkout_url)):
            if (self.app.config.options.get('checkout_url') or '') != checkout_url:
                M.AuditLog.log('{}: set "{}" {} => {}'.format(
                    self.app.config.options['mount_point'], "checkout_url",
                    self.app.config.options.get('checkout_url'), checkout_url))
                self.app.config.options.checkout_url = checkout_url
                flash("Checkout URL successfully changed")
        else:
            flash("%s is not a valid path for this repository" %
                  checkout_url, "error")
        if 'external_checkout_url' not in c.form_errors:
            if (self.app.config.options.get('external_checkout_url') or '') != external_checkout_url:
                M.AuditLog.log('{}: set "{}" {} => {}'.format(
                    self.app.config.options['mount_point'], "external_checkout_url",
                    self.app.config.options.get('external_checkout_url'), external_checkout_url))
                self.app.config.options.external_checkout_url = external_checkout_url
                flash("External checkout URL successfully changed")
        else:
            flash("Invalid external checkout URL: %s" % c.form_errors['external_checkout_url'], "error")


class SVNImportController(BaseController, AdminControllerMixin):
    import_form = widgets.ImportForm()

    def __init__(self, app):
        self.app = app

    @with_trailing_slash
    @expose('jinja:forgesvn:templates/svn/import.html')
    def index(self, **kw):
        c.is_empty = self.app.repo.is_empty()
        c.form = self.import_form
        return dict()

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(import_form, error_handler=index)
    def do_import(self, checkout_url=None, **kwargs):
        if self.app.repo.is_empty():
            with h.push_context(
                    self.app.config.project_id,
                    app_config_id=self.app.config._id):
                allura.tasks.repo_tasks.reclone.post(
                    cloned_from_path=None,
                    cloned_from_name=None,
                    cloned_from_url=checkout_url)
                M.AuditLog.log('{}: import initiated from "{}"'.format(
                    self.app.config.options['mount_point'], checkout_url))

            M.Notification.post_user(
                c.user, self.app.repo, 'importing',
                text='''Repository import scheduled,
                        an email notification will be sent when complete.''')
        else:
            M.Notification.post_user(
                c.user, self.app.repo, 'error',
                text="Can't import into non empty repository.")
        redirect(six.ensure_text(request.referer or '/'))


class SVNCommitBrowserController(BaseController):

    @without_trailing_slash
    @expose('json:')
    def commit_browser_data(self, start=None, limit=None, **kw):
        data = {
            'commits': [],
            'next_column': 1,
            'max_row': 0,
            'built_tree': {},
            'next_commit': None,
        }
        limit, _ = h.paging_sanitizer(limit or 100, 0, 0)
        for i, commit in enumerate(c.app.repo.log(revs=start, id_only=False, limit=limit+1)):
            if i >= limit:
                data['next_commit'] = str(commit['id'])
                break
            data['commits'].append(str(commit['id']))
            data['built_tree'][commit['id']] = {
                'column': 0,
                'parents': list(map(str, commit['parents'])),
                'short_id': '[r%s]' % commit['id'],
                'message': commit['message'],
                'oid': str(commit['id']),
                'row': i,
                'url': c.app.repo.url_for_commit(commit['id']),
            }
        data['max_row'] = len(data['commits']) - 1
        return data


def svn_timers():
    return Timer(
        'svn_lib.{method_name}', SM.svn.SVNLibWrapper, 'checkout', 'add',
        'checkin', 'info2', 'log', 'cat', 'list')


def forgesvn_timers():
    return Timer('svn_tool.{method_name}', SM.svn.SVNImplementation, '*')
