from tg import expose, validate, redirect, flash, request

from allura.app import Application, SitemapEntry, DefaultAdminController
from allura import model as M
from allura.lib.security import require_access, has_access
from allura.lib import helpers as h
from allura.controllers import BaseController
from allura.lib.widgets import form_fields as ffw

from webob import exc
import pylons
from pylons import c, g
from datetime import datetime
from formencode import validators
from formencode.compound import All

from forgeshorturl.model.shorturl import ShortUrl
from forgeshorturl.widgets.short_url import CreateShortUrlWidget

import logging


log = logging.getLogger(__name__)


class W:
    page_list = ffw.PageList()
    page_size = ffw.PageSize()
    create_short_url_lightbox = \
        CreateShortUrlWidget(name='create_short_url',
                             trigger='#sidebar a.create_short_url')


class ForgeShortUrlApp(Application):
    permissions = ['create ', 'update', 'view_private']
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
            links += [SitemapEntry('Add Short URL',
                      c.project.url() +
                      'admin/' +
                      self.config.options.mount_point +
                      '/add/',
                      ui_icon=g.icons['plus'],
                      className="create_short_url")]
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
        role_admin = M.ProjectRole.by_name('Admin')._id
        self.config.acl = [
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

    @expose()
    def _lookup(self, pname, *remainder):
        if request.method == 'GET':
            short_url = ShortUrl.query.find({'app_config_id': c.app.config._id,
                                             'short_name': pname}).first()
            if short_url:
                redirect(short_url.url)

        flash("We're sorry but we weren't able "
              "to process this request.", "error")
        raise exc.HTTPNotFound()


class ShortURLAdminController(DefaultAdminController):
    def __init__(self, app):
        self.app = app

    @expose()
    def index(self, **kw):
        redirect(c.project.url() + 'admin/tools')

    @expose('jinja:forgeshorturl:templates/add.html')
    @validate(dict(full_url=All(validators.URL(add_http=True),
                                validators.NotEmpty()),
                   short_url=validators.NotEmpty()))
    def add(self, short_url="",
            full_url="",
            description="",
            private="off", **kw):
        if (request.method == 'POST'):
            if pylons.c.form_errors:
                error_msg = "Error creating Short URL: "
                for msg in list(pylons.c.form_errors):
                    names = {"short_url": "Short name", "full_url": "Full URL"}
                    error_msg += "%s - %s " % (names[msg], c.form_errors[msg])
                    flash(error_msg, "error")
                redirect(request.referer)

            if (short_url != full_url):
                shorturl = ShortUrl.query.find({
                    'short_name': short_url,
                    'project_id': c.project._id}).first()
                if shorturl is None:
                    shorturl = ShortUrl()
                    shorturl.created = datetime.utcnow()
                    log_msg = 'create short url %s for %s' %\
                              (short_url,
                               full_url)
                else:
                    log_msg = 'update short url %s from %s to %s' %\
                              (short_url,
                               shorturl.url,
                               full_url)
                shorturl.url = full_url
                shorturl.short_name = short_url
                shorturl.description = description
                shorturl.create_user = c.user._id
                shorturl.app_config_id = self.app.config._id
                if private == "on":
                    shorturl.private = True
                else:
                    shorturl.private = False
                shorturl.last_updated = datetime.utcnow()
                M.AuditLog.log(log_msg)
                flash("Short url created")
            else:
                flash("Error creating Short URL: "
                      "Short Name and Full URL must be different", "error")
            redirect(request.referer)
        return dict(app=self.app)
