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

import json
import logging
import os
from pprint import pformat

import six
from six.moves.urllib.parse import unquote, urlencode

# Non-stdlib imports
from tg import expose, validate, redirect, flash, jsonify
from tg.decorators import with_trailing_slash, without_trailing_slash
from tg import tmpl_context as c, app_globals as g
from tg import request
from formencode import validators
from webob import exc
from ming.orm import session

# Pyforge-specific imports
from allura import model as M
from allura.lib import helpers as h
from allura.lib import validators as v
from allura.app import Application, SitemapEntry, DefaultAdminController, ConfigOption
from allura.lib.search import search_app
from allura.lib.decorators import require_post, memorable_forget
from allura.lib.security import require_access, has_access
from allura.lib.utils import is_ajax, JSONForExport, permanent_redirect
from allura.tasks import notification_tasks
from allura.lib import exceptions as forge_exc
from allura.controllers import AppDiscussionController, BaseController, AppDiscussionRestController
from allura.controllers import DispatchIndex
from allura.controllers import attachments as ac
from allura.controllers.feed import FeedArgs, FeedController
from allura.controllers.rest import AppRestControllerMixin
from allura.lib import widgets as w
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets.subscriptions import SubscribeForm
from allura.lib.widgets.search import SearchResults, SearchHelp

# Local imports
from forgewiki import model as WM
from forgewiki import version

log = logging.getLogger(__name__)


class W:
    thread = w.Thread(
        page=None, limit=None, page_size=None, count=None,
        style='linear')
    markdown_editor = ffw.MarkdownEdit()
    confirmation = ffw.Lightbox(name='confirm',
                                trigger='a.post-link',
                                options="{ modalCSS: { minHeight: 0, width: 'inherit', top: '150px'}}")
    label_edit = ffw.LabelEdit()
    attachment_add = ffw.AttachmentAdd()
    attachment_list = ffw.AttachmentList()
    subscribe_form = SubscribeForm()
    page_subscribe_form = SubscribeForm(thing='page')
    page_list = ffw.PageList()
    page_size = ffw.PageSize()
    search_results = SearchResults()
    help_modal = SearchHelp(fields={'title': 'title',
                                    'text': '"Page text"',
                                    'mod_date_dt': 'Last modified.  Example: mod_date_dt:[2018-01-01T00:00:00Z TO *]',
                                    'labels_t': 'labels',
                                    'author_user_name_t': 'username (for comments only)',
                                    })
    icons = {
        24: 'images/wiki_24.png',
        32: 'images/wiki_32.png',
        48: 'images/wiki_48.png'
    }


class ForgeWikiApp(Application):

    '''This is the Wiki app for PyForge'''
    __version__ = version.__version__
    permissions = ['configure', 'read', 'create', 'edit', 'delete',
                   'unmoderated_post', 'post', 'moderate', 'admin']
    permissions_desc = {
        'read': 'View wiki pages.',
        'create': 'Create wiki pages.',
        'edit': 'Edit wiki pages.',
        'delete': 'Delete wiki pages.',
        'admin': 'Set permissions. Configure options. Set wiki home page.',
    }
    config_options = Application.config_options + [
        ConfigOption('AllowEmailPosting', bool, True)
    ]
    searchable = True
    exportable = True
    tool_label = 'Wiki'
    tool_description = """
        Documentation is key to your project and the wiki tool
        helps make it easy for anyone to contribute.
    """
    default_mount_label = 'Wiki'
    default_mount_point = 'wiki'
    ordinal = 5
    default_root_page_name = 'Home'
    icons = {
        24: 'images/wiki_24.png',
        32: 'images/wiki_32.png',
        48: 'images/wiki_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.api_root = RootRestController()
        self.admin = WikiAdminController(self)

    def has_access(self, user, topic):
        return has_access(c.app, 'post')(user=user)

    def handle_message(self, topic, message):
        log.info('Message from %s (%s)',
                 topic, self.config.options.mount_point)
        log.info('Headers are: %s', message['headers'])
        page = WM.Page.find_page(topic)
        if page is None:
            page = WM.Page.find_page(topic.replace('_', ' '))
        if page is not None:
            self.handle_artifact_message(page, message)
        else:
            log.exception('Error getting artifact %s', topic)

    @property
    def root_page_name(self):
        globals = WM.Globals.query.get(app_config_id=self.config._id)
        if globals is not None:
            page_name = globals.root
        else:
            page_name = self.default_root_page_name
        return page_name

    @root_page_name.setter
    def root_page_name(self, new_root_page_name):
        globals = WM.Globals.query.get(app_config_id=self.config._id)
        if globals is not None:
            globals.root = new_root_page_name
        elif new_root_page_name != self.default_root_page_name:
            globals = WM.Globals(
                app_config_id=self.config._id, root=new_root_page_name)
        if globals is not None:
            session(globals).flush(globals)

    def default_root_page_text(self):
        return """Welcome to your wiki!

This is the default page, edit it as you see fit. To add a new page simply reference it within brackets, e.g.: [SamplePage].

The wiki uses [Markdown](%s) syntax.

[[members limit=20]]
""" % (self.url + 'markdown_syntax/')

    @property
    def show_discussion(self):
        return self.config.options.get('show_discussion', True)

    @show_discussion.setter
    def show_discussion(self, show):
        self.config.options['show_discussion'] = bool(show)

    @property
    def show_left_bar(self):
        return self.config.options.get('show_left_bar', True)

    @show_left_bar.setter
    def show_left_bar(self, show):
        self.config.options['show_left_bar'] = bool(show)

    @property
    def show_right_bar(self):
        return self.config.options.get('show_right_bar', True)

    @show_right_bar.setter
    def show_right_bar(self, show):
        self.config.options['show_right_bar'] = bool(show)

    @property
    def allow_email_posting(self):
        return self.config.options.get('AllowEmailPosting', True)

    @allow_email_posting.setter
    def allow_email_posting(self, show):
        self.config.options['AllowEmailPosting'] = bool(show)

    def main_menu(self):
        """Apps should provide their entries to be added to the main nav
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        """
        return [SitemapEntry(
            self.config.options.mount_label,
            '.')]

    def sitemap_xml(self):
        """
        Used for generating sitemap.xml.
        If the root page has default content, omit it from the sitemap.xml.
        Assumes :attr:`main_menu` will return an entry pointing to the root page.
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        """
        root_page = WM.Page.query.get(app_config_id=self.config._id, title=self.root_page_name)
        if self.should_noindex_page(root_page):
            return []
        return self.main_menu()

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label
        with h.push_config(c, app=self):
            pages = [
                SitemapEntry(p.title, p.url())
                for p in WM.Page.query.find(dict(
                    app_config_id=self.config._id,
                    deleted=False))]
            return [
                SitemapEntry(menu_id, '.')[SitemapEntry('Pages')[pages]]]

    def should_noindex_page(self, page: WM.Page) -> bool:
        """Checks whether a page should not be indexed."""
        if not page:
            # this shouldn't happen; just a safeguard for using `page` below
            return False
        elif (page['title'] == self.default_root_page_name and page['version'] == 1) \
                or page['text'] in ('You can edit this description', ):
            # If page has default name (i.e. 'Home') and has not been edited, noindex.
            # or old default text
            # but not if comments are visible
            visible_comments = page.discussion_thread.find_posts(status='ok', limit=1)
            return not visible_comments
        else:
            return False

    def create_common_wiki_menu(self, has_create_access, admin_menu=False):
        links = []
        if has_create_access:
            links += [SitemapEntry('Create Page', self.url + 'create_wiki_page/',
                                   ui_icon=g.icons['add'],
                                   className='admin_modal')]
        if not admin_menu:
            links += [SitemapEntry(''),
                      SitemapEntry('Wiki Home', self.url, className='wiki_home')]
        links += [SitemapEntry('Browse Pages', self.url + 'browse_pages/'),
                  SitemapEntry('Browse Labels', self.url + 'browse_tags/')]
        discussion = self.config.discussion
        pending_mod_count = M.Post.query.find({
            'discussion_id': discussion._id,
            'status': 'pending',
            'deleted': False
        }).count() if discussion else 0
        if pending_mod_count and h.has_access(discussion, 'moderate')():
            links.append(
                SitemapEntry(
                    'Moderate', discussion.url() + 'moderate', ui_icon=g.icons['moderate'],
                    small=pending_mod_count))
        if not c.user.is_anonymous() and not admin_menu:
            subscribed = M.Mailbox.subscribed(app_config_id=self.config._id)
            subscribe_action = 'unsubscribe' if subscribed else 'subscribe'
            subscribe_title = '{}{}'.format(
                subscribe_action.capitalize(),
                '' if subscribed else ' to wiki')
            subscribe_url = '{}#toggle-{}'.format(self.url + 'subscribe', subscribe_action)
            links.append(SitemapEntry(None))
            links.append(SitemapEntry(subscribe_title, subscribe_url, ui_icon=g.icons['mail']))
        if not admin_menu:
            links += [SitemapEntry(''),
                      SitemapEntry('Formatting Help', '/nf/markdown_syntax',
                                   extra_html_attrs={'target': '_blank', 'rel': 'nofollow'})]
        return links

    def admin_menu(self, skip_common_menu=False):
        links = [SitemapEntry('Set Home',
                              self.admin_url + 'home',
                              className='admin_modal')]

        if not self.show_left_bar and not skip_common_menu:
            links += self.create_common_wiki_menu(has_create_access=True, admin_menu=True)
        links += super().admin_menu(force_options=True)
        return links

    @h.exceptionless([], log)
    def sidebar_menu(self):
        return self.create_common_wiki_menu(has_create_access=has_access(self, 'create'))

    def sidebar_menu_js(self):
        return '''
        $('#sidebar').on('click', 'a[href$="#toggle-subscribe"]', function(e) {
            e.preventDefault();
            var link = this;
            var data = {
                _session_id: $.cookie('_session_id'),
                subscribe: '1'
            };
            $.post(this.href, data, function(){
                $('#messages').notify('Subscribed to wiki.');
                $('span', link).text('Unsubscribe');
                $(link).attr('href', $(link).attr('href').replace('-subscribe','-unsubscribe'));
            });
        });
        $('#sidebar').on('click', 'a[href$="#toggle-unsubscribe"]', function(e) {
            e.preventDefault();
            var link = this;
            var data = {
                _session_id: $.cookie('_session_id'),
                unsubscribe: '1'
            };
            $.post(this.href, data, function(){
                $('#messages').notify('Unsubscribed.');
                $('span', link).text('Subscribe to wiki');
                $(link).attr('href', $(link).attr('href').replace('-unsubscribe','-subscribe'));
            });
        });
        '''

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project.name
        super().install(project)
        # Setup permissions
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_developer = M.ProjectRole.by_name('Developer')._id
        role_member = M.ProjectRole.by_name('Member')._id
        role_auth = M.ProjectRole.by_name('*authenticated')._id
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_auth, 'post'),
            M.ACE.allow(role_auth, 'unmoderated_post'),
            M.ACE.allow(role_member, 'create'),
            M.ACE.allow(role_member, 'edit'),
            M.ACE.allow(role_developer, 'delete'),
            M.ACE.allow(role_developer, 'moderate'),
            M.ACE.allow(role_admin, 'configure'),
            M.ACE.allow(role_admin, 'admin'),
        ]
        root_page_name = self.default_root_page_name
        WM.Globals(app_config_id=c.app.config._id, root=root_page_name)
        self.upsert_root(root_page_name, notify=False)

    def upsert_root(self, new_root, notify=True):
        p = WM.Page.query.get(app_config_id=self.config._id,
                              title=new_root, deleted=False)
        if p is None:
            with h.push_config(c, app=self), h.notifications_disabled(c.project, disabled=not notify):
                p = WM.Page.upsert(new_root)
                p.text = self.default_root_page_text()
                p.commit()

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        WM.WikiAttachment.query.remove(dict(app_config_id=self.config._id))
        WM.Page.query.remove(dict(app_config_id=self.config._id))
        WM.Globals.query.remove(dict(app_config_id=self.config._id))
        super().uninstall(project)

    def bulk_export(self, f, export_path='', with_attachments=False):
        f.write('{"pages": [')
        pages = list(WM.Page.query.find(dict(
            app_config_id=self.config._id,
            deleted=False)))
        if with_attachments:
            GenericClass = JSONForExport
            self.export_attachments(pages, export_path)
        else:
            GenericClass = jsonify.JSONEncoder
        for i, page in enumerate(pages):
            if i > 0:
                f.write(',')
            json.dump(page, f, cls=GenericClass, indent=2)
        f.write(']}')

    def export_attachments(self, pages, export_path):
        for page in pages:
            attachment_path = self.get_attachment_export_path(export_path, str(page._id))
            self.save_attachments(attachment_path, page.attachments)

            for post in page.discussion_thread.query_posts(status='ok'):
                post_path = os.path.join(
                    attachment_path,
                    page.discussion_thread._id,
                    post.slug
                )
                self.save_attachments(post_path, post.attachments)


class RootController(BaseController, DispatchIndex, FeedController):

    def __init__(self):
        self._discuss = AppDiscussionController()

    def catch_all(self, *args, **kw):
        url = '/{}/?{}'.format(request.controller_url, urlencode(kw))
        redirect(h.urlquote(h.really_unicode(url)))

    def _check_security(self):
        require_access(c.app, 'read')

    @with_trailing_slash
    @expose()
    def index(self, **kw):
        permanent_redirect(h.urlquote(h.really_unicode(c.app.root_page_name) + '/'))

    @expose()
    def _lookup(self, pname, *remainder):
        """Instantiate a Page object, and continue dispatch there."""
        return PageController(pname), remainder

    @expose()
    def new_page(self, title):
        redirect(h.urlquote(h.really_unicode(title) + '/'))

    @with_trailing_slash
    @expose('jinja:forgewiki:templates/wiki/search.html')
    @validate(dict(q=v.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False),
                   search_comments=validators.StringBool(if_empty=False),
                   project=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None, search_comments=None, project=None, limit=None, page=0, **kw):
        'local wiki search'
        c.search_results = W.search_results
        c.help_modal = W.help_modal
        search_params = kw
        search_params.update({
            'q': q or '',
            'history': history,
            'search_comments': search_comments,
            'project': project,
            'limit': limit,
            'page': page,
            'allowed_types': ['WikiPage', 'WikiPage Snapshot'],
        })
        return search_app(**search_params)

    @with_trailing_slash
    @expose('jinja:forgewiki:templates/wiki/browse.html')
    @validate(dict(sort=v.UnicodeString(if_empty='alpha'),
                   show_deleted=validators.StringBool(if_empty=False),
                   page=validators.Int(if_empty=0, if_invalid=0),
                   limit=validators.Int(if_empty=None, if_invalid=None)),
              error_handler=catch_all)
    def browse_pages(self, sort='alpha', show_deleted=False, page=0, limit=None, **kw):
        'list of all pages in the wiki'
        c.page_list = W.page_list
        c.page_size = W.page_size
        limit, pagenum, start = g.handle_paging(limit, page, default=25)
        count = 0
        pages = []
        uv_pages = []
        criteria = dict(app_config_id=c.app.config._id)
        can_delete = has_access(c.app, 'delete')()
        show_deleted = show_deleted and can_delete
        if not can_delete:
            criteria['deleted'] = False
        q = WM.Page.query.find(criteria)
        if sort == 'alpha':
            q = q.sort('title')
        count = q.count()
        q = q.skip(start).limit(int(limit))
        for page in q:
            recent_edit = page.history().first()
            p = dict(title=page.title, url=page.url(), deleted=page.deleted)
            if recent_edit:
                p['updated'] = recent_edit.timestamp
                p['user_label'] = recent_edit.author.display_name
                p['user_name'] = recent_edit.author.username
                pages.append(p)
            else:
                if sort == 'recent':
                    uv_pages.append(p)
                else:
                    pages.append(p)
        if sort == 'recent':
            pages.sort(reverse=True, key=lambda x: (x['updated']))
            pages = pages + uv_pages
        h1_text = f"{c.project.name} {c.app.config.options.mount_label} - Browse Pages"
        return dict(
            pages=pages, can_delete=can_delete, show_deleted=show_deleted,
            limit=limit, count=count, page=pagenum, h1_text=h1_text)

    @with_trailing_slash
    @expose('jinja:forgewiki:templates/wiki/browse_tags.html')
    @validate(dict(sort=v.UnicodeString(if_empty='alpha'),
                   page=validators.Int(if_empty=0, if_invalid=0),
                   limit=validators.Int(if_empty=None, if_invalid=None)))
    def browse_tags(self, sort='alpha', page=0, limit=None, **kw):
        'list of all labels in the wiki'
        c.page_list = W.page_list
        c.page_size = W.page_size
        limit, pagenum, start = g.handle_paging(limit, page, default=25)
        count = 0
        page_tags = {}
        q = WM.Page.query.find(dict(app_config_id=c.app.config._id,
                                    deleted=False,
                                    labels={'$ne': []}))
        for page in q:
            if page.labels:
                for label in page.labels:
                    if label not in page_tags:
                        page_tags[label] = []
                    page_tags[label].append(page)
        count = len(page_tags)
        name_labels = sorted(page_tags)
        h1_text = f"{c.project.name} {c.app.config.options.mount_label} - Browse Labels"
        return dict(labels=page_tags,
                    limit=limit,
                    count=count,
                    page=pagenum,
                    name_labels=name_labels[start:start + limit],
                    h1_text=h1_text)

    @with_trailing_slash
    @expose('jinja:forgewiki:templates/wiki/create_page.html')
    def create_wiki_page(self, **kw):
        return {}

    @expose()
    def markdown_syntax(self, **kw):
        permanent_redirect('/nf/markdown_syntax')

    @expose()
    @require_post()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None):
        if subscribe:
            M.Mailbox.subscribe(type='direct')
        elif unsubscribe:
            M.Mailbox.unsubscribe()
        redirect(six.ensure_text(request.referer or '/'))


class PageController(BaseController, FeedController):

    def __init__(self, title):
        self.title = h.really_unicode(unquote(title))
        self.page = WM.Page.query.get(
            app_config_id=c.app.config._id, title=self.title)
        if self.page is not None:
            self.attachment = WikiAttachmentsController(self.page)

    def _check_security(self):
        if self.page:
            require_access(self.page, 'read')
            if self.page.deleted:
                require_access(self.page, 'delete')
        elif has_access(c.app, 'create'):
            self.rate_limit(WM.Page, 'Page create/edit')
        else:
            raise exc.HTTPNotFound

    def fake_page(self):
        return dict(
            title=self.title,
            text='',
            labels=[],
            viewable_by=['all'],
            attachments=[])

    def get_version(self, version):
        if not version:
            return self.page
        try:
            return self.page.get_version(version)
        except (ValueError, IndexError):
            return None

    @expose()
    def _lookup(self, pname, *remainder):
        page = WM.Page.query.get(
            app_config_id=c.app.config._id, title=pname)
        if page:
            redirect(page.url())
        else:
            raise exc.HTTPNotFound

    @with_trailing_slash
    @expose('jinja:forgewiki:templates/wiki/page_view.html')
    @validate(dict(version=validators.Int(if_empty=None, if_invalid=None),
                   page=validators.Int(if_empty=0, if_invalid=0),
                   limit=validators.Int(if_empty=None, if_invalid=None)))
    def index(self, version=None, page=0, limit=None, **kw):
        if not self.page:
            redirect(c.app.url + h.urlquote(self.title) + '/edit')
        c.confirmation = W.confirmation
        c.thread = W.thread
        c.attachment_list = W.attachment_list
        c.subscribe_form = W.page_subscribe_form
        post_count = self.page.discussion_thread.post_count
        limit, pagenum, _ = g.handle_paging(limit, page)
        limit, pagenum = h.paging_sanitizer(limit, pagenum, post_count)
        page = self.get_version(version)
        if page is None:
            if version:
                redirect('.?version=%d' % (version - 1))
            else:
                redirect('.')
        cur = page.version
        if cur > 1:
            prev = cur - 1
        else:
            prev = None
        next = cur + 1
        hide_left_bar = not (c.app.show_left_bar)
        subscribed_to_page = M.Mailbox.subscribed(artifact=self.page)
        latest_version = self.page.history().limit(1).first()
        is_latest_version = cur == latest_version.version
        return dict(
            page=page,
            cur=cur, prev=prev, next=next,
            page_subscribed=subscribed_to_page,
            hide_left_bar=hide_left_bar, show_meta=c.app.show_right_bar,
            pagenum=pagenum, limit=limit, count=post_count,
            noindex=c.app.should_noindex_page(self.page),
            is_latest_version=is_latest_version,)

    @without_trailing_slash
    @expose('jinja:forgewiki:templates/wiki/page_edit.html')
    def edit(self):
        page_exists = self.page
        if self.page:
            require_access(self.page, 'edit')
            page = self.page
        else:
            page = self.fake_page()
        self.rate_limit(WM.Page, 'Page create/edit')  # check before trying to save
        c.confirmation = W.confirmation
        c.markdown_editor = W.markdown_editor
        c.attachment_add = W.attachment_add
        c.attachment_list = W.attachment_list
        c.label_edit = W.label_edit
        hide_left_bar = not c.app.show_left_bar
        return dict(page=page,
                    page_exists=page_exists,
                    hide_left_bar=hide_left_bar,
                    subscribed_to_tool=M.Mailbox.subscribed(),
                    )

    @without_trailing_slash
    @expose('json:')
    @require_post()
    def delete(self, **kw):
        require_access(self.page, 'delete')
        M.AuditLog.log('{}: deleted wiki page "{}"'.format(
            c.app.config.options['mount_point'],
            self.page.title,
        ))
        self.page.delete()
        return dict(location='../' + self.page.title + '/?deleted=True')

    @without_trailing_slash
    @expose('json:')
    @require_post()
    def undelete(self, **kw):
        require_access(self.page, 'delete')
        self.page.deleted = False
        M.AuditLog.log('{}: undeleted wiki page "{}"'.format(
            c.app.config.options['mount_point'],
            self.page.title,
        ))
        M.Shortlink.from_artifact(self.page)
        return dict(location='./edit')

    @without_trailing_slash
    @expose('jinja:forgewiki:templates/wiki/page_history.html')
    @validate(dict(page=validators.Int(if_empty=0, if_invalid=0),
                   limit=validators.Int(if_empty=None, if_invalid=None)))
    def history(self, page=0, limit=None, **kw):
        if not self.page:
            raise exc.HTTPNotFound
        c.page_list = W.page_list
        c.page_size = W.page_size
        c.confirmation = W.confirmation
        limit, pagenum, start = g.handle_paging(limit, page, default=25)
        count = 0
        pages = self.page.history()
        count = pages.count()
        pages = pages.skip(start).limit(int(limit))
        return dict(title=self.title, pages=pages,
                    limit=limit, count=count, page=pagenum)

    @without_trailing_slash
    @expose('jinja:forgewiki:templates/wiki/page_diff.html')
    @validate(dict(
        v1=validators.Int(),
        v2=validators.Int()))
    def diff(self, v1, v2, **kw):
        if not self.page:
            raise exc.HTTPNotFound
        p1 = self.get_version(v1)
        p2 = self.get_version(v2)
        result = h.diff_text(p1.text, p2.text)
        return dict(p1=p1, p2=p2, edits=result)

    @without_trailing_slash
    @expose(content_type='text/plain')
    def raw(self):
        if not self.page:
            raise exc.HTTPNotFound
        return pformat(self.page)

    def get_feed(self, project, app, user):
        """Return a :class:`allura.controllers.feed.FeedArgs` object describing
        the xml feed for this controller.

        Overrides :meth:`allura.controllers.feed.FeedController.get_feed`.

        """
        if not self.page:
            return None
        return FeedArgs(
            {'ref_id': self.page.index_id()},
            'Recent changes to %s' % self.page.title,
            self.page.url())

    @without_trailing_slash
    @expose('json:')
    @require_post()
    @validate(dict(version=validators.Int(if_empty=1, if_invalid=1)))
    def revert(self, version, **kw):
        if not self.page:
            raise exc.HTTPNotFound
        require_access(self.page, 'edit')
        orig = self.get_version(version)
        if orig:
            self.page.text = orig.text
        self.page.commit()
        return dict(location='.')

    @memorable_forget()
    @without_trailing_slash
    @h.vardec
    @expose()
    @require_post()
    def update(self, title=None, text=None,
               labels=None,
               subscribe=False,
               **kw):
        activity_verb = 'created'
        if not title:
            flash('You must provide a title for the page.', 'error')
            redirect('edit')
        title = title.replace('/', '-')
        self.rate_limit(WM.Page, 'Page create/edit')
        if not self.page:
            # the page doesn't exist yet, so create it
            self.page = WM.Page.upsert(self.title)
            M.AuditLog.log('{}: created new wiki page "{}"'.format(
                c.app.config.options['mount_point'],
                self.page.title,
            ))
        else:
            require_access(self.page, 'edit')
            activity_verb = 'modified'
        name_conflict = None
        if self.page.title != title:
            name_conflict = WM.Page.query.find(
                dict(app_config_id=c.app.config._id, title=title, deleted=False)).first()
            if name_conflict:
                flash('There is already a page named "%s".' % title, 'error')
            else:
                if self.page.title == c.app.root_page_name:
                    WM.Globals.query.get(
                        app_config_id=c.app.config._id).root = title
                M.AuditLog.log('{}: renamed wiki page "{}" => "{}"'.format(
                    c.app.config.options['mount_point'],
                    self.page.title,
                    title,
                ))
                self.page.title = title
                activity_verb = 'renamed'
        old_text = self.page.text
        self.page.text = text
        if labels:
            self.page.labels = labels.split(',')
        else:
            self.page.labels = []
        self.page.commit(subscribe=subscribe)
        g.spam_checker.check(title + '\n' + text, artifact=self.page,
                             user=c.user, content_type='wiki')
        if activity_verb == 'created':
            notification_tasks.send_usermentions_notification.post(self.page.index_id(), text)
        elif activity_verb == 'modified':
            notification_tasks.send_usermentions_notification.post(self.page.index_id(), text, old_text)
        g.director.create_activity(c.user, activity_verb, self.page,
                                   related_nodes=[c.project], tags=['wiki'])
        redirect('../' + h.urlquote(h.really_unicode(self.page.title)) + ('/' if not name_conflict else '/edit'))

    @without_trailing_slash
    @expose('json:')
    @require_post()
    def update_markdown(self, text=None, **kw):
        if has_access(self.page, 'edit'):
            self.page.text = text
            self.page.commit()
            g.spam_checker.check(text, artifact=self.page, user=c.user, content_type='wiki')
            g.director.create_activity(c.user, 'modified', self.page, related_nodes=[c.project], tags=['wiki'])
            return {
                'status': 'success'
            }
        else:
            return {
                'status': 'no_permission'
            }

    @without_trailing_slash
    @expose()
    def get_markdown(self):
        return self.page.text

    @without_trailing_slash
    @expose()
    @require_post()
    def attach(self, file_info=None, **kw):
        if not self.page:
            raise exc.HTTPNotFound
        require_access(self.page, 'edit')
        self.page.add_multiple_attachments(file_info)
        if is_ajax(request):
            return
        redirect(six.ensure_text(request.referer or '/'))

    @expose('json:')
    @require_post()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None, **kw):
        if not self.page:
            raise exc.HTTPNotFound
        if subscribe:
            self.page.subscribe(type='direct')
        elif unsubscribe:
            self.page.unsubscribe()
        return {
            'status': 'ok',
            'subscribed': M.Mailbox.subscribed(artifact=self.page),
            'subscribed_to_tool': M.Mailbox.subscribed(),
            'subscribed_to_entire_name': 'wiki',
        }


class WikiAttachmentController(ac.AttachmentController):
    AttachmentClass = WM.WikiAttachment
    edit_perm = 'edit'


class WikiAttachmentsController(ac.AttachmentsController):
    AttachmentControllerClass = WikiAttachmentController


class RootRestController(BaseController, AppRestControllerMixin):

    def __init__(self):
        self._discuss = AppDiscussionRestController()

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('json:')
    def index(self, **kw):
        page_titles = []
        pages = WM.Page.query.find(
            dict(app_config_id=c.app.config._id, deleted=False))
        for page in pages:
            if has_access(page, 'read')():
                page_titles.append(page.title)
        return dict(pages=page_titles)

    @expose()
    def _lookup(self, title, *remainder):
        return PageRestController(title), remainder


class PageRestController(BaseController):

    def __init__(self, title):
        self.title = h.really_unicode(unquote(title)) if title else None
        self.page = WM.Page.query.get(app_config_id=c.app.config._id,
                                      title=self.title,
                                      deleted=False)

    def _check_security(self):
        if self.page:
            require_access(self.page, 'read')
            if self.page.deleted:
                require_access(self.page, 'delete')

    @h.vardec
    @expose('json:')
    def index(self, **kw):
        if request.method == 'POST':
            return self._update_page(self.title, **kw)
        if self.page is None:
            raise exc.HTTPNotFound()
        return self.page.__json__(posts_limit=10)

    def _update_page(self, title, **post_data):
        with h.notifications_disabled(c.project):
            if not self.page:
                require_access(c.app, 'create')
                if WM.Page.is_limit_exceeded(c.app.config, user=c.user):
                    log.warn('Page create/edit rate limit exceeded. %s',
                             c.app.config.url())
                    raise forge_exc.HTTPTooManyRequests()
                self.page = WM.Page.upsert(title)
                self.page.viewable_by = ['all']
            else:
                require_access(self.page, 'edit')
            self.page.text = post_data['text']
            if 'labels' in post_data:
                self.page.labels = post_data['labels'].split(',')
            self.page.commit()
            return {}


class WikiAdminController(DefaultAdminController):

    def _check_security(self):
        require_access(self.app, 'configure')

    @with_trailing_slash
    def index(self, **kw):
        redirect('home')

    @without_trailing_slash
    @expose('jinja:forgewiki:templates/wiki/admin_home.html')
    def home(self):
        return dict(app=self.app,
                    home=self.app.root_page_name,
                    allow_config=has_access(self.app, 'configure')())

    @without_trailing_slash
    @expose('jinja:forgewiki:templates/wiki/admin_options.html')
    def options(self):
        return dict(app=self.app,
                    allow_config=has_access(self.app, 'configure')())

    @without_trailing_slash
    @expose()
    @require_post()
    def set_home(self, new_home):
        old_home = self.app.root_page_name
        self.app.root_page_name = new_home
        self.app.upsert_root(new_home)
        flash('Home updated')
        mount_base = c.project.url() + \
            self.app.config.options.mount_point + '/'
        url = h.really_unicode(mount_base) + h.really_unicode(new_home) + '/'
        M.AuditLog.log('{}: set home page "{}" => "{}"'.format(
            self.app.config.options['mount_point'],
            old_home,
            new_home,
        ))
        redirect(h.urlquote(url))

    @without_trailing_slash
    @expose()
    @require_post()
    def set_options(self, show_discussion=False, show_left_bar=False, show_right_bar=False,
                    allow_email_posting=False):
        mount_point = self.app.config.options['mount_point']

        if self.app.show_discussion != bool(show_discussion):
            M.AuditLog.log('{}: set option "{}" {} => {}'.format(
                mount_point, "Show Discussion", self.app.show_discussion, bool(show_discussion)))
            self.app.show_discussion = show_discussion

        if self.app.show_left_bar != bool(show_left_bar):
            M.AuditLog.log('{}: set option "{}" {} => {}'.format(
                mount_point, "Show left Bar", self.app.show_left_bar, bool(show_left_bar)))
            self.app.show_left_bar = show_left_bar

        if self.app.show_right_bar != bool(show_right_bar):
            M.AuditLog.log('{}: set option "{}" {} => {}'.format(
                mount_point, "Show metadata", self.app.show_right_bar, bool(show_right_bar)))
            self.app.show_right_bar = show_right_bar

        if self.app.allow_email_posting != bool(allow_email_posting):
            M.AuditLog.log('{}: set option "{}" {} => {}'.format(
                mount_point, "Allow posting replies via email", self.app.allow_email_posting, bool(allow_email_posting)))
            self.app.allow_email_posting = allow_email_posting

        flash('Wiki options updated')
        redirect(six.ensure_text(request.referer or '/'))
