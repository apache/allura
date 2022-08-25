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
from six.moves.urllib.parse import quote

from tg import tmpl_context as c, app_globals as g
from tg import request
from tg import expose, redirect, flash, validate, config
from tg.decorators import with_trailing_slash, without_trailing_slash
from webob import exc
from bson import ObjectId
from paste.deploy.converters import asbool

from ming.utils import LazyProperty

import allura.tasks
from allura import version
from allura.controllers.base import BaseController
from allura.lib import helpers as h
from allura import model as M
from allura.lib import security
from allura.lib.decorators import require_post
from allura.lib.security import has_access
from allura.lib import validators as v
from allura.app import Application, SitemapEntry, DefaultAdminController, ConfigOption

log = logging.getLogger(__name__)


class RepositoryApp(Application):
    END_OF_REF_ESCAPE = '~'
    __version__ = version.__version__
    permissions = [
        'read', 'write', 'create',
        'unmoderated_post', 'post', 'moderate', 'admin',
        'configure']
    permissions_desc = {
        'read': 'Browse repo via web UI. Removing read does not prevent direct repo read access.',
        'write': 'Repo push access.',
        'create': 'Not used.',
        'admin': 'Set permissions, default branch, and viewable files.',
    }
    config_options = Application.config_options + [
        ConfigOption('cloned_from_project_id', ObjectId, None),
        ConfigOption('cloned_from_repo_id', ObjectId, None),
        ConfigOption('init_from_url', str, None),
        ConfigOption('external_checkout_url', str, None)
    ]
    tool_label = 'Repository'
    default_mount_label = 'Code'
    default_mount_point = 'code'
    relaxed_mount_points = True
    ordinal = 2
    forkable = False
    default_branch_name = None  # master or default or some such
    repo = None  # override with a property in child class
    icons = {
        24: 'images/code_24.png',
        32: 'images/code_32.png',
        48: 'images/code_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.admin = RepoAdminController(self)
        self.admin_api_root = RepoAdminRestController(self)

    def main_menu(self):
        '''Apps should provide their entries to be added to the main nav
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        '''
        return [SitemapEntry(
            self.config.options.mount_label,
            '.')]

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()]]

    def admin_menu(self):
        admin_url = c.project.url() + 'admin/' + \
            self.config.options.mount_point + '/'
        links = [
            SitemapEntry(
                'Checkout URL',
                c.project.url() + 'admin/' +
                self.config.options.mount_point +
                '/' + 'checkout_url',
                className='admin_modal'),
            SitemapEntry(
                'Viewable Files',
                admin_url + 'extensions',
                className='admin_modal'),
            SitemapEntry(
                'Refresh Repository',
                c.project.url() +
                self.config.options.mount_point +
                '/refresh'),
        ]
        links += super().admin_menu()
        [links.remove(l) for l in links[:] if l.label == 'Options']
        return links

    @h.exceptionless([], log)
    def sidebar_menu(self):
        if not self.repo or self.repo.status != 'ready':
            return []
        links = []
        if not self.repo.is_empty():
            links.append(SitemapEntry('Browse Commits', c.app.url + 'commit_browser',
                                      ui_icon=g.icons['browse_commits'],
                                      extra_html_attrs=dict(rel='nofollow')))
        if self.forkable and self.repo.status == 'ready' and not self.repo.is_empty():
            links.append(
                SitemapEntry('Fork', c.app.url + 'fork', ui_icon=g.icons['fork'],
                             extra_html_attrs=dict(rel='nofollow')))
        merge_request_count = self.repo.merge_requests_by_statuses(
            'open').count()
        if self.forkable:
            links += [
                SitemapEntry(
                    'Merge Requests', c.app.url + 'merge-requests/',
                    small=merge_request_count,
                    extra_html_attrs=dict(rel='nofollow'))]
        if self.repo.forks:
            links += [
                SitemapEntry('Forks', c.app.url + 'forks/',
                             small=len(self.repo.forks),
                             extra_html_attrs=dict(rel='nofollow'))
            ]

        has_upstream_repo = False
        if self.repo.upstream_repo.name:
            try:
                self.repo.push_upstream_context()
            except Exception:
                log.warn('Could not get upstream repo (perhaps it is gone) for: %s %s',
                         self.repo, self.repo.upstream_repo.name, exc_info=True)
            else:
                has_upstream_repo = True

        if has_upstream_repo:
            repo_path_parts = self.repo.upstream_repo.name.strip(
                '/').split('/')
            links += [
                SitemapEntry('Clone of'),
                SitemapEntry('%s / %s' %
                             (repo_path_parts[1], repo_path_parts[-1]),
                             self.repo.upstream_repo.name)
            ]
            if not c.app.repo.is_empty() and has_access(c.app.repo, 'admin'):
                merge_url = c.app.url + 'request_merge'
                if getattr(c, 'revision', None):
                    merge_url = merge_url + '?branch=' + h.urlquote(c.revision)
                links.append(SitemapEntry('Request Merge', merge_url,
                             ui_icon=g.icons['merge'], extra_html_attrs=dict(rel='nofollow')
                                          ))
            pending_upstream_merges = self.repo.pending_upstream_merges()
            if pending_upstream_merges:
                links.append(SitemapEntry(
                    'Pending Merges',
                    self.repo.upstream_repo.name + 'merge-requests/',
                    small=pending_upstream_merges, extra_html_attrs=dict(rel='nofollow')))
        ref_url = self.repo.url_for_commit(
            self.default_branch_name, url_type='ref')
        branches = self.repo.get_branches()
        if branches:
            links.append(SitemapEntry('Branches'))
            for branch in branches:
                if branch.name == self.default_branch_name:
                    branches.remove(branch)
                    branches.insert(0, branch)
                    break
            max_branches = 10
            for branch in branches[:max_branches]:
                links.append(SitemapEntry(
                    branch.name,
                    h.urlquote(self.repo.url_for_commit(branch.name) + 'tree/'),
                    extra_html_attrs=dict(rel='nofollow')))
            if len(branches) > max_branches:
                links.append(
                    SitemapEntry(
                        'More Branches',
                        ref_url + 'branches/',
                        extra_html_attrs=dict(rel='nofollow')
                    ))
        elif not self.repo.is_empty():
            # SVN repos, for example, should have a sidebar link to get to the main view
            links.append(
                SitemapEntry('Browse Files', c.app.url, extra_html_attrs=dict(rel='nofollow'))
            )

        tags = self.repo.get_tags()
        if tags:
            links.append(SitemapEntry('Tags'))
            max_tags = 10
            for b in tags[:max_tags]:
                links.append(SitemapEntry(
                    b.name,
                    h.urlquote(self.repo.url_for_commit(b.name) + 'tree/'), 
                    extra_html_attrs=dict(rel='nofollow')))
            if len(tags) > max_tags:
                links.append(
                    SitemapEntry(
                        'More Tags',
                        ref_url + 'tags/',
                        extra_html_attrs=dict(rel='nofollow')
                    ))
        return links

    def install(self, project):
        self.config.options['project_name'] = project.name
        super().install(project)
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_developer = M.ProjectRole.by_name('Developer')._id
        role_auth = M.ProjectRole.authenticated()._id
        role_anon = M.ProjectRole.anonymous()._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_auth, 'post'),
            M.ACE.allow(role_auth, 'unmoderated_post'),
            M.ACE.allow(role_developer, 'create'),
            M.ACE.allow(role_developer, 'write'),
            M.ACE.allow(role_developer, 'moderate'),
            M.ACE.allow(role_admin, 'configure'),
            M.ACE.allow(role_admin, 'admin'),
        ]

    def uninstall(self, project):
        allura.tasks.repo_tasks.uninstall.post()

    def __json__(self):
        data = super().__json__()
        repo: M.Repository = self.repo
        if repo:
            for clone_cat in repo.clone_command_categories(anon=c.user.is_anonymous()):
                respkey = 'clone_url_' + clone_cat['key']
                data[respkey] = repo.clone_url(clone_cat['key'],
                                               username='' if c.user.is_anonymous() else c.user.username,
                                               )
        return data


class RepoAdminController(DefaultAdminController):

    @LazyProperty
    def repo(self):
        return self.app.repo

    def _check_security(self):
        security.require_access(self.app, 'configure')

    @with_trailing_slash
    @expose()
    def index(self, **kw):
        redirect('extensions')

    @without_trailing_slash
    @expose('jinja:allura:templates/repo/admin_extensions.html')
    def extensions(self, **kw):
        return dict(app=self.app,
                    allow_config=True,
                    additional_viewable_extensions=getattr(self.repo, 'additional_viewable_extensions', ''))

    @without_trailing_slash
    @expose()
    @require_post()
    def set_extensions(self, **post_data):
        self.repo.additional_viewable_extensions = post_data['additional_viewable_extensions']
        redirect(six.ensure_text(request.referer or '/'))

    @without_trailing_slash
    @expose('jinja:allura:templates/repo/default_branch.html')
    def set_default_branch_name(self, branch_name=None, **kw):
        if (request.method == 'POST') and branch_name:
            self.repo.set_default_branch(branch_name)
            redirect(six.ensure_text(request.referer or '/'))
        else:
            return dict(app=self.app,
                        default_branch_name=self.app.default_branch_name)

    @without_trailing_slash
    @expose('jinja:allura:templates/repo/checkout_url.html')
    def checkout_url(self):
        return dict(app=self.app,
                    merge_allowed=not asbool(config.get(f'scm.merge.{self.app.config.tool_name}.disabled')),
                    )

    @without_trailing_slash
    @expose()
    @require_post()
    @validate({'external_checkout_url': v.NonHttpUrl})
    def set_checkout_url(self, **post_data):
        flash_msgs = []
        external_checkout_url = (post_data.get('external_checkout_url') or '').strip()
        if 'external_checkout_url' not in c.form_errors:
            if (self.app.config.options.get('external_checkout_url') or '') != external_checkout_url:
                M.AuditLog.log('{}: set "{}" {} => {}'.format(
                    self.app.config.options['mount_point'], "external_checkout_url",
                    self.app.config.options.get('external_checkout_url'), external_checkout_url))
                self.app.config.options.external_checkout_url = external_checkout_url
                flash_msgs.append("External checkout URL successfully changed.")
        else:
            flash_msgs.append("Invalid external checkout URL: %s." % c.form_errors['external_checkout_url'])

        merge_disabled = bool(post_data.get('merge_disabled'))
        if merge_disabled != self.app.config.options.get('merge_disabled', False):
            M.AuditLog.log('{}: set "{}" {} => {}'.format(
                self.app.config.options['mount_point'], "merge_disabled",
                self.app.config.options.get('merge_disabled', False), merge_disabled))
            self.app.config.options.merge_disabled = merge_disabled
            flash_msgs.append('One-click merge {}.'.format('disabled' if merge_disabled else 'enabled'))

        if flash_msgs:
            message = ' '.join(flash_msgs)
            flash(message,
                  'error' if 'Invalid' in message else 'ok')

        redirect(six.ensure_text(request.referer or '/'))


class RepoAdminRestController(BaseController):
    def __init__(self, app):
        self.app = app
        self.webhooks = RestWebhooksLookup(app)


class RestWebhooksLookup(BaseController):
    def __init__(self, app):
        self.app = app

    @expose('json:')
    def index(self, **kw):
        webhooks = self.app._webhooks
        if len(webhooks) == 0:
            raise exc.HTTPNotFound()
        configured_hooks = M.Webhook.query.find({
            'type': {'$in': [wh.type for wh in webhooks]},
            'app_config_id': self.app.config._id}
        ).sort('_id', 1).all()
        limits = {
            wh.type: {
                'max': M.Webhook.max_hooks(wh.type, self.app.config.tool_name),
                'used': M.Webhook.query.find({
                    'type': wh.type,
                    'app_config_id': self.app.config._id,
                }).count(),
            } for wh in webhooks
        }
        return {'webhooks': [hook.__json__() for hook in configured_hooks],
                'limits': limits}

    @expose()
    def _lookup(self, name, *remainder):
        for hook in self.app._webhooks:
            if hook.type == name and hook.api_controller:
                return hook.api_controller(hook, self.app), remainder
        raise exc.HTTPNotFound(name)
