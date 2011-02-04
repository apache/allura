'''IRC Chatbot Plugin
'''
#-*- python -*-
import logging
from datetime import date, time, datetime, timedelta

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, flash
from tg.decorators import with_trailing_slash
from pylons import g, c, request
from formencode import validators

# Pyforge-specific imports
from allura.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from allura.lib import helpers as h
from allura.lib.search import search
from allura.lib.decorators import audit, react, require_post
from allura.lib.security import require, has_artifact_access
from allura.model import ProjectRole
from allura.controllers import BaseController

# Local imports
from forgechat import model as CM
from forgechat import version

log = logging.getLogger(__name__)

class ForgeChatApp(Application):
    __version__ = version.__version__
    tool_label='Chat'
    status='alpha'
    default_mount_label='Chat'
    default_mount_point='chat'
    ordinal=13
    installable = True
    permissions = ['configure', 'read' ]
    config_options = Application.config_options + [
        ConfigOption('channel', str, ''),
        ]
    icons={
        24:'allura/images/chat_24.png',
        32:'allura/images/chat_32.png',
        48:'allura/images/chat_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = AdminController(self)

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    @h.exceptionless([], log)
    def sidebar_menu(self):
        return [
            SitemapEntry('Home', '.'),
            SitemapEntry('Search', 'search'),
            ]

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = [
            SitemapEntry('Options',
                         admin_url + 'options',
                         className='admin_modal'),
            SitemapEntry('Permissions',
                         admin_url + 'permissions/',
                         className='nav_child'),
            ]
        return links

    def install(self, project):
        'Set up any default permissions and roles here'
        super(ForgeChatApp, self).install(project)

        # Give the installing user all the permissions
        pr = c.user.project_role()
        for perm in self.permissions:
              self.config.acl[perm] = [ pr._id ]
        self.config.acl['read'].append(ProjectRole.anonymous()._id)
        CM.ChatChannel(
            project_id=self.config.project_id,
            app_config_id=self.config._id,
            channel=self.config.options['channel'])

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        CM.ChatChannel.query.remove(dict(
                project_id=self.config.project_id,
                app_config_id=self.config._id))
        super(ForgeChatApp, self).uninstall(project)

class AdminController(DefaultAdminController):

    @with_trailing_slash
    def index(self, **kw):
        redirect(c.project.url()+'admin/tools')

    @expose()
    @require_post()
    def configure(self, channel=None):
        with h.push_config(c, app=self.app):
            require(has_artifact_access('configure', app=self.app),
                    'Must have configure permission')
            chan = CM.ChatChannel.query.get(
                project_id=self.app.config.project_id,
                app_config_id=self.app.config._id)
            chan.channel = channel
        flash('Chat options updated')
        super(AdminController, self).configure(channel=channel)

class RootController(BaseController):

    @expose()
    def index(self, **kw):
        now = datetime.utcnow()
        redirect(c.app.url + now.strftime('%Y/%m/%d/'))

    @expose('jinja:chat/search.html')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None):
        'local tool search'
        results = []
        count=0
        if not q:
            q = ''
        else:
            results = search(
                q,
                fq=[
                    'is_history_b:%s' % history,
                    'project_id_s:%s' % c.project._id,
                    'mount_point_s:%s'% c.app.config.options.mount_point ])
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

    @expose()
    def _lookup(self, y, m, d, *rest):
        y,m,d = int(y), int(m), int(d)
        return DayController(date(y,m,d)), rest

class DayController(RootController):

    def __init__(self, day):
        self.day = day

    @expose('jinja:chat/day.html')
    def index(self, **kw):
        q = dict(
            timestamp={
                '$gte':datetime.combine(self.day, time.min),
                '$lte':datetime.combine(self.day, time.max)})
        messages = CM.ChatMessage.query.find(q).sort('timestamp').all()
        prev = c.app.url + (self.day - timedelta(days=1)).strftime('%Y/%m/%d/')
        next = c.app.url + (self.day + timedelta(days=1)).strftime('%Y/%m/%d/')
        return dict(
            day=self.day,
            messages=messages,
            prev=prev,
            next=next)
