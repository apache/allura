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


import six
from tg import expose, validate, redirect, flash, request
from tg.decorators import without_trailing_slash

from allura.app import Application, SitemapEntry, DefaultAdminController
from allura import model as M
from allura.lib.security import require_access, has_access
from allura.lib import helpers as h
from allura.lib import validators as v
from allura.lib.search import search_app
from allura.controllers import BaseController
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets.search import SearchResults, SearchHelp

from webob import exc
from tg import tmpl_context as c, app_globals as g
from datetime import datetime
from formencode import validators
from formencode.compound import All

from forgeshorturl.model.shorturl import ShortUrl
import forgeshorturl.widgets.short_url as suw

import logging


log = logging.getLogger(__name__)


class W:
    search_results = SearchResults()
    search_help = SearchHelp(comments=False, history=False)
    page_list = ffw.PageList()
    page_size = ffw.PageSize()
    short_url_lightbox = suw.ShortUrlFormWidget()


class ForgeShortUrlApp(Application):
    permissions = ['read', 'create', 'update', 'view_private']
    permissions_desc = {
        'read': 'View public short urls.',
        'create': 'Create new short url. Requires admin permission.',
        'update': 'Edit/remove existing short url. Requires admin permission.',
        'view_private': 'View private short urls.',
    }
    max_instances = 0
    searchable = True
    tool_label = 'URL shortener'
    default_mount_label = 'URL shortener'
    default_mount_point = 'url'
    sitemap = []
    ordinal = 14
    icons = {
        24: 'images/ext_24.png',
        32: 'images/ext_32.png',
        48: 'images/ext_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = ShortURLAdminController(self)

    def is_visible_to(self, user):
        '''Whether the user can view the app.'''
        return has_access(c.project, 'create')(user=user)

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label
        return [SitemapEntry(menu_id, '.')]

    def admin_menu(self):
        links = []
        if has_access(c.app, "create"):
            links = [SitemapEntry('Add Short URL',
                                  c.project.url() +
                                  'admin/' +
                                  self.config.options.mount_point +
                                  '/add/',
                                  className='admin_modal'), ]
            links += [SitemapEntry('Browse',
                                   c.project.url() +
                                   self.config.options.mount_point), ]

        links += super().admin_menu()
        return links

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project.name
        super().install(project)
        # Setup permissions
        role_anon = M.ProjectRole.anonymous()._id
        role_admin = M.ProjectRole.by_name('Admin')._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_admin, 'create'),
            M.ACE.allow(role_admin, 'update'),
            M.ACE.allow(role_admin, 'view_private'),
            M.ACE.allow(role_admin, 'configure'), ]

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        ShortUrl.query.remove(dict(app_config_id=c.app.config._id))
        super().uninstall(project)


class RootController(BaseController):

    def __init__(self):
        c.short_url_lightbox = W.short_url_lightbox

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('jinja:forgeshorturl:templates/index.html')
    @validate(dict(page=validators.Int(if_empty=0, if_invalid=0),
                   limit=validators.Int(if_empty=None, if_invalid=None)))
    def index(self, page=0, limit=None, **kw):
        c.page_list = W.page_list
        c.page_size = W.page_size
        limit, pagenum, start = g.handle_paging(limit, page, default=100)
        p = {'app_config_id': c.app.config._id}
        if not has_access(c.app, 'view_private'):
            p['private'] = False
        short_urls = (ShortUrl.query.find(p))
        count = short_urls.count()

        short_urls = short_urls.skip(start).limit(limit)

        return {
            'short_urls': short_urls,
            'limit': limit,
            'pagenum': pagenum,
            'count': count,
            'url_len': len(ShortUrl.build_short_url(c.app, short_name='')),
        }

    @expose('jinja:forgeshorturl:templates/search.html')
    @validate(dict(q=v.UnicodeString(if_empty=None),
                   project=validators.StringBool(if_empty=False)))
    def search(self, q=None, project=None, limit=None, page=0, **kw):
        c.search_results = W.search_results
        c.help_modal = W.search_help
        search_params = kw
        search_params.update({
            'q': q or '',
            'project': project,
            'limit': limit,
            'page': page,
            'allowed_types': ['ShortUrl'],
        })
        if not has_access(c.app, 'view_private'):
            search_params['fq'] = ['private_b:False']
        d = search_app(**search_params)
        d['search_comments_disable'] = True
        d['search_history_disable'] = True
        d['url_len'] = len(ShortUrl.build_short_url(c.app, short_name=''))
        return d

    @expose()
    def _lookup(self, pname, *remainder):
        query = {'app_config_id': c.app.config._id,
                 'short_name': pname}
        if not has_access(c.app, 'view_private'):
            query['private'] = False
        short_url = ShortUrl.query.find(query).first()
        if short_url:
            redirect(short_url.full_url)
        raise exc.HTTPNotFound()


class ShortURLAdminController(DefaultAdminController):

    shorturl_validators = All(
        validators.NotEmpty(),
        validators.Regex(
            r'^[-_a-zA-Z0-9]+$',
            messages={'invalid':
                      'must include only letters, numbers, dashes and underscores.'}
        )
    )

    @expose()
    def index(self, **kw):
        redirect(six.ensure_text(request.referer or '/'))

    @without_trailing_slash
    @expose('json:')
    def remove(self, shorturl, **kw):
        require_access(self.app, 'update')
        ShortUrl.query.remove({
            'app_config_id': self.app.config._id,
            'short_name': shorturl})
        return dict(status='ok')

    @expose('jinja:forgeshorturl:templates/form.html')
    @validate(dict(full_url=All(validators.URL(add_http=True),
                                validators.NotEmpty()),
                   short_url=shorturl_validators))
    def add(self, short_url='', full_url='', description='', private='off',
            update=False, **kw):
        if update:
            require_access(self.app, 'update')
        else:
            require_access(self.app, 'create')
        if request.method == 'POST':
            if c.form_errors:
                error_msg = 'Error: '
                for msg in list(c.form_errors):
                    names = {'short_url': 'Short url', 'full_url': 'Full URL'}
                    error_msg += f'{names[msg]}: {c.form_errors[msg]} '
                    flash(error_msg, 'error')
                redirect(six.ensure_text(request.referer or '/'))

            shorturl = ShortUrl.query.find({
                'app_config_id': self.app.config._id,
                'short_name': short_url}).first()

            if shorturl is not None:
                if not update:
                    flash('Short url %s already exists' % short_url, 'error')
                    redirect(six.ensure_text(request.referer or '/'))
                else:
                    msg = ('update short url %s from %s to %s'
                           % (short_url, shorturl.full_url, full_url))
                    flash("Short url updated")

            else:
                shorturl = ShortUrl()
                shorturl.created = datetime.utcnow()
                shorturl.app_config_id = self.app.config._id
                msg = f'create short url {short_url} for {full_url}'
                flash("Short url created")

            shorturl.short_name = short_url
            shorturl.full_url = full_url
            shorturl.description = description
            shorturl.create_user = c.user._id
            shorturl.private = private == 'on'
            shorturl.last_updated = datetime.utcnow()

            M.AuditLog.log(msg)
            redirect(six.ensure_text(request.referer or '/'))
        return dict(
            app=self.app,
            url_len=len(ShortUrl.build_short_url(c.app, short_name='')))
