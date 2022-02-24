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

'''IRC Chatbot Plugin
'''
import logging
from datetime import date, time, datetime, timedelta

# Non-stdlib imports
import six
from tg import expose, validate, redirect, flash
from tg.decorators import with_trailing_slash
from tg import tmpl_context as c, request
from formencode import validators
from ming.utils import LazyProperty

# Pyforge-specific imports
from allura.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from allura.lib import helpers as h
from allura.lib import validators as v
from allura.lib.search import search_app
from allura.lib.decorators import require_post
from allura.lib.security import require_access
from allura.lib.widgets.search import SearchResults, SearchHelp
from allura import model as M
from allura.controllers import BaseController

# Local imports
from forgechat import model as CM
from forgechat import version

log = logging.getLogger(__name__)


class ForgeChatApp(Application):
    __version__ = version.__version__
    tool_label = 'Chat'
    tool_description = 'IRC chat integration'
    status = 'alpha'
    default_mount_label = 'Chat'
    default_mount_point = 'chat'
    ordinal = 13
    permissions = ['configure', 'read']
    permissions_desc = {
        'configure': 'Set monitored IRC channel. Requires admin permission.',
        'read': 'View chat logs.',
    }
    config_options = Application.config_options + [
        ConfigOption('channel', str, ''),
    ]
    has_notifications = False
    icons = {
        24: 'images/chat_24.png',
        32: 'images/chat_32.png',
        48: 'images/chat_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = AdminController(self)

    @LazyProperty
    def channel(self):
        return CM.ChatChannel.query.get(app_config_id=self.config._id)

    def main_menu(self):
        return [SitemapEntry(self.config.options.mount_label, '.')]

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()]]

    @h.exceptionless([], log)
    def sidebar_menu(self):
        return [
            SitemapEntry('Home', '.'),
            SitemapEntry('Search', 'search'),
        ]

    def admin_menu(self):
        return super().admin_menu()

    def install(self, project):
        'Set up any default permissions and roles here'
        super().install(project)
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_anon = M.ProjectRole.anonymous()._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_admin, 'configure'),
        ]
        CM.ChatChannel(
            project_id=self.config.project_id,
            app_config_id=self.config._id,
            channel=self.config.options['channel'])

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        CM.ChatChannel.query.remove(dict(
            project_id=self.config.project_id,
            app_config_id=self.config._id))
        super().uninstall(project)


class AdminController(DefaultAdminController):

    @with_trailing_slash
    def index(self, **kw):
        redirect(six.ensure_text(request.referer or '/'))

    @expose()
    @require_post()
    def configure(self, channel=None):
        with h.push_config(c, app=self.app):
            require_access(self.app, 'configure')
            chan = CM.ChatChannel.query.get(
                project_id=self.app.config.project_id,
                app_config_id=self.app.config._id)
            chan.channel = channel
        flash('Chat options updated')
        super().configure(channel=channel)


class RootController(BaseController):

    @expose()
    def index(self, **kw):
        now = datetime.utcnow()
        redirect(c.app.url + now.strftime('%Y/%m/%d/'))

    @with_trailing_slash
    @expose('jinja:forgechat:templates/chat/search.html')
    @validate(dict(q=v.UnicodeString(if_empty=None),
                   project=validators.StringBool(if_empty=False)))
    def search(self, q=None, project=None, limit=None, page=0, **kw):
        c.search_results = SearchResults()
        c.help_modal = SearchHelp(comments=False, history=False,
                                  fields={'sender_t': 'username',
                                          'text': '"Message text"',
                                          })
        search_params = kw
        search_params.update({
            'q': q or '',
            'project': project,
            'limit': limit,
            'page': page,
            'allowed_types': ['Chat Message'],
        })
        d = search_app(**search_params)
        d['search_comments_disable'] = True
        d['search_history_disable'] = True
        return d

    @expose()
    def _lookup(self, y, m, d, *rest):
        y, m, d = int(y), int(m), int(d)
        return DayController(date(y, m, d)), rest


class DayController(RootController):

    def __init__(self, day):
        self.day = day

    @expose('jinja:forgechat:templates/chat/day.html')
    def index(self, **kw):
        q = dict(
            timestamp={
                '$gte': datetime.combine(self.day, time.min),
                '$lte': datetime.combine(self.day, time.max)})
        messages = CM.ChatMessage.query.find(q).sort('timestamp').all()
        prev = c.app.url + (self.day - timedelta(days=1)).strftime('%Y/%m/%d/')
        next = c.app.url + (self.day + timedelta(days=1)).strftime('%Y/%m/%d/')
        return dict(
            day=self.day,
            messages=messages,
            prev=prev,
            next=next)
