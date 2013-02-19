from tg import expose, validate, redirect, flash, request
from tg.decorators import without_trailing_slash
from urllib import urlencode

from allura.app import Application, SitemapEntry, DefaultAdminController
from allura import model as M
from allura.lib.security import require_access, has_access
from allura.lib import helpers as h
from allura.lib.search import search, SearchError
from allura.controllers import BaseController
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets.search import SearchResults

from webob import exc
import pylons
from pylons import tmpl_context as c, app_globals as g
from datetime import datetime
from formencode import validators
from formencode.compound import All

from forgeshorturl.model.shorturl import ShortUrl
import forgeshorturl.widgets.short_url as suw

import logging


log = logging.getLogger(__name__)


class W:
    search_results = SearchResults()
    page_list = ffw.PageList()
    page_size = ffw.PageSize()
    create_short_url_lightbox = suw.CreateShortUrlWidget(
            name='create_short_url',
            trigger='#sidebar a.add_short_url')
    update_short_url_lightbox = suw.UpdateShortUrlWidget()


class ForgeShortUrlApp(Application):
    permissions = ['read', 'create', 'update', 'view_private']
    searchable = True
    tool_label = 'URL shortener'
    default_mount_label = 'URL shortener'
    default_mount_point = 'url'
    sitemap = []
    ordinal = 14
    installable = False
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
        menu_id = self.config.options.mount_label.title()
        return [SitemapEntry(menu_id, '.')[self.sidebar_menu()]]

    def sidebar_menu(self):
        links = []
        if has_access(c.app, "create"):
            url = '%sadmin/%s/add/' % \
                  (c.project.url(), self.config.options.mount_point)
            links = [SitemapEntry('Add Short URL',
                                  url,
                                  ui_icon=g.icons['plus'],
                                  className="add_short_url"), ]
        return links

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

        links += super(ForgeShortUrlApp, self).admin_menu()
        return links

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project.name
        super(ForgeShortUrlApp, self).install(project)
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
        super(ForgeShortUrlApp, self).uninstall(project)


class RootController(BaseController):
    def __init__(self):
        c.create_short_url_lightbox = W.create_short_url_lightbox
        c.update_short_url_lightbox = W.update_short_url_lightbox

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('jinja:forgeshorturl:templates/index.html')
    @validate(dict(page=validators.Int(if_empty=0),
                   limit=validators.Int(if_empty=100)))
    def index(self, page=0, limit=100, **kw):
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
            'count': count
        }

    @expose('jinja:forgeshorturl:templates/search.html')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False),
                   project=validators.StringBool(if_empty=False)))
    def search(self, q=None,
               history=None, project=None,
               limit=None, page=0, **kw):
        if project:
            redirect(c.project.url() +
                     'search?' +
                     urlencode(dict(q=q, history=history)))
        results = []
        search_error = None
        count = 0
        limit, page, start = g.handle_paging(limit, page, default=25)
        if not q:
            q = ''
        else:
            query = ['is_history_b:%s' % history,
                    'project_id_s:%s' % c.project._id,
                    'mount_point_s:%s' % c.app.config.options.mount_point,
                    'type_s:%s' % ShortUrl.type_s]
            if not has_access(c.app, 'view_private'):
                query.append('private_b:False')
            try:
                results = search(q, fq=query, short_timeout=True, ignore_errors=False)
            except SearchError as e:
                search_error = e

            if results:
                count = results.hits
        c.search_results = W.search_results
        return dict(q=q, history=history, results=results or [],
                    count=count, limit=limit, page=page, search_error=search_error)

    @expose()
    def _lookup(self, pname, *remainder):
        if request.method == 'GET':
            query = {'app_config_id': c.app.config._id,
                     'short_name': pname}
            if not has_access(c.app, 'view_private'):
                query['private'] = False
            short_url = ShortUrl.query.find(query).first()
            if short_url:
                redirect(short_url.full_url)

        flash("We're sorry but we weren't able "
              "to process this request.", "error")
        raise exc.HTTPNotFound()


class ShortURLAdminController(DefaultAdminController):
    def __init__(self, app):
        self.app = app

    @expose()
    def index(self, **kw):
        redirect(c.project.url() + 'admin/tools')

    @without_trailing_slash
    @expose('json:')
    def remove(self, shorturl):
        require_access(self.app, 'update')
        ShortUrl.query.remove({
            'app_config_id': self.app.config._id,
            'short_name': shorturl})
        return dict(status='ok')

    @expose('jinja:forgeshorturl:templates/add.html')
    @validate(dict(full_url=All(validators.URL(add_http=True),
                                validators.NotEmpty()),
                   short_url=validators.NotEmpty()))
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
                    error_msg += '%s: %s ' % (names[msg], c.form_errors[msg])
                    flash(error_msg, 'error')
                redirect(request.referer)

            shorturl = ShortUrl.query.find({
                'app_config_id': self.app.config._id,
                'short_name': short_url}).first()

            if shorturl is not None:
                if not update:
                    flash('Short url %s already exists' % short_url, 'error')
                    redirect(request.referer)
                else:
                    msg = ('update short url %s from %s to %s'
                            % (short_url, shorturl.full_url, full_url))
                    flash("Short url updated")

            else:
                shorturl = ShortUrl()
                shorturl.created = datetime.utcnow()
                shorturl.app_config_id = self.app.config._id
                msg = 'create short url %s for %s' % (short_url, full_url)
                flash("Short url created")

            shorturl.short_name = short_url
            shorturl.full_url = full_url
            shorturl.description = description
            shorturl.create_user = c.user._id
            shorturl.private = private == 'on'
            shorturl.last_updated = datetime.utcnow()

            M.AuditLog.log(msg)
            redirect(request.referer)
        return dict(app=self.app)
