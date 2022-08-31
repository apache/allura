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
import six.moves.urllib.parse
import six.moves.urllib.request
import six.moves.urllib.error
import json

# Non-stdlib imports
import pymongo
from tg import config, expose, validate, redirect, flash, jsonify
from tg.decorators import with_trailing_slash, without_trailing_slash
from tg import tmpl_context as c
from tg import app_globals as g
from tg import request
from paste.deploy.converters import asbool
import formencode
from formencode import validators
from webob import exc

from ming.orm import session

# Allura-specific imports
from allura.app import Application, SitemapEntry, ConfigOption
from allura.app import DefaultAdminController
from allura.lib import helpers as h
from allura.lib import validators as v
from allura.lib.utils import JSONForExport
from allura.tasks import notification_tasks
from allura.lib.search import search_app
from allura.lib.decorators import require_post, memorable_forget
from allura.lib.security import has_access, require_access
from allura.lib import widgets as w
from allura.lib import exceptions as forge_exc
from allura.lib.widgets.subscriptions import SubscribeForm
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets.search import SearchResults, SearchHelp
from allura import model as M
from allura.controllers import BaseController, AppDiscussionController, AppDiscussionRestController
from allura.controllers.attachments import AttachmentController, AttachmentsController
from allura.controllers.rest import AppRestControllerMixin
from allura.controllers.feed import FeedArgs, FeedController

# Local imports
from forgeblog import model as BM
from forgeblog import version
from forgeblog import widgets
import six

log = logging.getLogger(__name__)


class W:
    thread = w.Thread(
        page=None, limit=None, page_size=None, count=None,
        style='linear')
    pager = widgets.BlogPager()
    new_post_form = widgets.NewPostForm()
    edit_post_form = widgets.EditPostForm()
    view_post_form = widgets.ViewPostForm()
    attachment_list = ffw.AttachmentList()
    confirmation = ffw.Lightbox(name='confirm',
                                trigger='a.post-link',
                                options="{ modalCSS: { minHeight: 0, width: 'inherit', top: '150px'}}")
    preview_post_form = widgets.PreviewPostForm()
    subscribe_form = SubscribeForm(thing='post')
    search_results = SearchResults()
    help_modal = SearchHelp(fields={'title': 'Title',
                                    'text': '"Post text"',
                                    'labels_t': 'Labels',
                                    'mod_date_dt': 'Last modified.  Example: mod_date_dt:[2018-01-01T00:00:00Z TO *]',
                                    'author_user_name_t': 'username (for comments only)',
                                    })


class ForgeBlogApp(Application):
    __version__ = version.__version__
    tool_label = 'Blog'
    tool_description = """
        Share exciting news and progress updates with your
        community.
    """
    default_mount_label = 'Blog'
    default_mount_point = 'blog'
    permissions = ['configure', 'read', 'write',
                   'unmoderated_post', 'post', 'moderate', 'admin']
    permissions_desc = {
        'read': 'View blog entries.',
        'write': 'Create new blog entry.',
        'admin': 'Set permissions. Enable/disable commenting.',
    }
    config_options = Application.config_options + [
        ConfigOption('AllowEmailPosting', bool, True)
    ]
    ordinal = 14
    exportable = True
    searchable = True
    config_options = Application.config_options
    default_external_feeds = []
    icons = {
        24: 'images/blog_24.png',
        32: 'images/blog_32.png',
        48: 'images/blog_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = BlogAdminController(self)
        self.api_root = RootRestController()

    @property
    def external_feeds_list(self):
        globals = BM.Globals.query.get(app_config_id=self.config._id)
        if globals is not None:
            external_feeds = globals.external_feeds
        else:
            external_feeds = self.default_external_feeds
        return external_feeds

    @external_feeds_list.setter
    def external_feeds_list(self, new_external_feeds):
        globals = BM.Globals.query.get(app_config_id=self.config._id)
        if globals is not None:
            globals.external_feeds = new_external_feeds
        elif len(new_external_feeds) > 0:
            globals = BM.Globals(
                app_config_id=self.config._id, external_feeds=new_external_feeds)
        if globals is not None:
            session(globals).flush()

    def main_menu(self):
        return [SitemapEntry(self.config.options.mount_label, '.')]

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()]]

    def sitemap_xml(self):
        """
        Used for generating sitemap.xml.
        If the root page has default content, omit it from the sitemap.xml.
        Assumes :attr:`main_menu` will return an entry pointing to the root page.
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        """
        if self.should_noindex():
            return []
        return self.main_menu()

    def should_noindex(self):
        post = BM.BlogPost.query.get(
            app_config_id=self.config._id,
            state='published',
            deleted=False)
        if post:
            return False
        return True

    @property
    def show_discussion(self):
        if 'show_discussion' in self.config.options:
            return self.config.options['show_discussion']
        else:
            return True

    @property
    def allow_email_posting(self):
        return self.config.options.get('AllowEmailPosting', True)

    @allow_email_posting.setter
    def allow_email_posting(self, show):
        self.config.options['AllowEmailPosting'] = bool(show)

    @h.exceptionless([], log)
    def sidebar_menu(self):
        base = c.app.url
        links = [
            SitemapEntry('Home', base),
        ]
        if has_access(self, 'write')():
            links += [SitemapEntry('New Post', base + 'new')]
        return links

    def admin_menu(self):
        admin_url = c.project.url() + 'admin/' + \
            self.config.options.mount_point + '/'
        # temporarily disabled until some bugs are fixed
        links = super().admin_menu(force_options=True)
        # We don't want external feeds in menu unless they're enabled
        if asbool(config.get('forgeblog.exfeed', 'false')):
            links.insert(0, SitemapEntry('External feeds',
                         admin_url + 'exfeed', className='admin_modal'))
        return links
        # return super(ForgeBlogApp, self).admin_menu(force_options=True)

    def install(self, project):
        'Set up any default permissions and roles here'
        super().install(project)

        # Setup permissions
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_developer = M.ProjectRole.by_name('Developer')._id
        role_auth = M.ProjectRole.by_name('*authenticated')._id
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_auth, 'post'),
            M.ACE.allow(role_auth, 'unmoderated_post'),
            M.ACE.allow(role_developer, 'write'),
            M.ACE.allow(role_developer, 'moderate'),
            M.ACE.allow(role_admin, 'configure'),
            M.ACE.allow(role_admin, 'admin'),
        ]

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        BM.BlogAttachment.query.remove(dict(app_config_id=c.app.config._id))
        BM.BlogPost.query.remove(dict(app_config_id=c.app.config._id))
        BM.BlogPostSnapshot.query.remove(dict(app_config_id=c.app.config._id))
        super().uninstall(project)

    def bulk_export(self, f, export_path='', with_attachments=False):
        f.write('{"posts": [')
        posts = list(BM.BlogPost.query.find(dict(app_config_id=self.config._id)))
        if with_attachments:
            JSONEncoder = JSONForExport
            self.export_attachments(posts, export_path)
        else:
            JSONEncoder = jsonify.JSONEncoder
        for i, post in enumerate(posts):
            if i > 0:
                f.write(',')
            json.dump(post, f, cls=JSONEncoder, indent=2)
        f.write(']}')

    def export_attachments(self, articles, export_path):
        for article in articles:
            for post in article.discussion_thread.query_posts(status='ok'):
                post_path = self.get_attachment_export_path(
                    export_path,
                    str(article._id),
                    article.discussion_thread._id,
                    post.slug
                )
                self.save_attachments(post_path, post.attachments)


class RootController(BaseController, FeedController):

    def __init__(self):
        self._discuss = AppDiscussionController()

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('jinja:forgeblog:templates/blog/index.html')
    @with_trailing_slash
    @validate(dict(page=validators.Int(if_empty=0, if_invalid=0),
                   limit=validators.Int(if_empty=None, if_invalid=None)))
    def index(self, page=0, limit=None, **kw):
        query_filter = dict(app_config_id=c.app.config._id)
        if not has_access(c.app, 'write')():
            query_filter['state'] = 'published'
        q = BM.BlogPost.query.find(query_filter)
        post_count = q.count()
        limit, page, _ = g.handle_paging(limit, page)
        limit, page = h.paging_sanitizer(limit, page, post_count)
        posts = q.sort('timestamp', pymongo.DESCENDING) \
                 .skip(page * limit).limit(limit)
        c.form = W.preview_post_form
        c.pager = W.pager
        return dict(posts=posts, page=page, limit=limit, count=post_count)

    @with_trailing_slash
    @expose('jinja:forgeblog:templates/blog/search.html')
    @validate(dict(q=v.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False),
                   search_comments=validators.StringBool(if_empty=False),
                   project=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None, search_comments=None, project=None, limit=None, page=0, **kw):
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
            'allowed_types': ['Blog Post', 'Blog Post Snapshot'],
            'fq': ['state_s:published']
        })
        return search_app(**search_params)

    @expose('jinja:forgeblog:templates/blog/edit_post.html')
    @without_trailing_slash
    def new(self, **kw):
        require_access(c.app, 'write')
        self.rate_limit(BM.BlogPost, 'Create/edit', c.app.config.url())
        post = dict(
            state='published')
        c.form = W.new_post_form
        return dict(post=post,
                    subscribed_to_tool=M.Mailbox.subscribed(),
                    )

    @memorable_forget()
    @expose()
    @require_post()
    # both new & edit submit here, but validate with new since it adds a field (subscribe)
    @validate(form=W.new_post_form, error_handler=new)
    @without_trailing_slash
    def save(self, **kw):
        require_access(c.app, 'write')
        self.rate_limit(BM.BlogPost, 'Create/edit', c.app.config.url())
        attachment = kw.pop('attachment', None)
        post = BM.BlogPost.new(**kw)
        g.spam_checker.check(kw['title'] + '\n' + kw['text'], artifact=post,
                             user=c.user, content_type='blog-post')
        if attachment is not None:
            post.add_multiple_attachments(attachment)
        notification_tasks.send_usermentions_notification.post(post.index_id(), kw['text'])
        redirect(h.urlquote(h.really_unicode(post.url())))

    @expose()
    def _lookup(self, year=None, month=None, name=None, *rest):
        if year is None or month is None or name is None:
            raise exc.HTTPNotFound()
        slug = '/'.join((year, month, six.ensure_text(six.moves.urllib.parse.unquote(name))))
        post = BM.BlogPost.query.get(slug=slug, app_config_id=c.app.config._id)
        if post is None:
            raise exc.HTTPNotFound()
        return PostController(post), rest

    def get_feed(self, project, app, user):
        """
        Return a :class:`allura.controllers.feed.FeedArgs` object describing the xml feed for this controller.
        Overrides :meth:`allura.controllers.feed.FeedController.get_feed`.
        """
        return FeedArgs(
            dict(project_id=project._id, app_config_id=app.config._id,
                 link=BM.BlogPost.link_regex
                 ),
            'Recent posts to %s' % app.config.options.mount_point,
            app.url)


class BlogAttachmentController(AttachmentController):
    AttachmentClass = BM.BlogAttachment


class BlogAttachmentsController(AttachmentsController):
    AttachmentControllerClass = BlogAttachmentController


class PostController(BaseController, FeedController):

    def __init__(self, post):
        self.post = post
        self.attachment = BlogAttachmentsController(self.post)

    def _check_security(self):
        require_access(self.post, 'read')
        if self.post.state == 'draft':
            require_access(self.post, 'write')

    @expose('jinja:forgeblog:templates/blog/post.html')
    @with_trailing_slash
    @validate(dict(page=validators.Int(if_empty=0, if_invalid=0),
                   limit=validators.Int(if_empty=None, if_invalid=None)))
    def index(self, page=0, limit=None, **kw):
        c.form = W.view_post_form
        c.attachment_list = W.attachment_list
        c.subscribe_form = W.subscribe_form
        c.thread = W.thread
        post_count = self.post.discussion_thread.post_count
        limit, page, _ = g.handle_paging(limit, page)
        limit, page = h.paging_sanitizer(limit, page, post_count)
        version = kw.pop('version', None)
        post = self._get_version(version)
        base_post = self.post
        subscribed = M.Mailbox.subscribed(artifact=self.post)
        return dict(post=post, base_post=base_post,
                    page=page, limit=limit, count=post_count,
                    subscribed=subscribed)

    @expose('jinja:forgeblog:templates/blog/edit_post.html')
    @without_trailing_slash
    def edit(self, **kw):
        require_access(self.post, 'write')
        self.rate_limit(BM.BlogPost, 'Create/edit', c.app.config.url())
        c.form = W.edit_post_form
        c.attachment_list = W.attachment_list
        return dict(post=self.post,
                    subscribed_to_tool=M.Mailbox.subscribed(),
                    )

    @without_trailing_slash
    @expose('jinja:forgeblog:templates/blog/post_history.html')
    def history(self, **kw):
        c.confirmation = W.confirmation
        posts = self.post.history()
        return dict(title=self.post.title, posts=posts)

    @without_trailing_slash
    @expose('jinja:forgeblog:templates/blog/post_diff.html')
    def diff(self, v1, v2, **kw):
        p1 = self._get_version(int(v1))
        p2 = self._get_version(int(v2))
        result = h.diff_text(p1.text, p2.text)
        return dict(p1=p1, p2=p2, edits=result)

    @memorable_forget()
    @expose()
    @require_post()
    @validate(form=W.edit_post_form, error_handler=edit)
    @without_trailing_slash
    def save(self, delete=None, **kw):
        require_access(self.post, 'write')
        self.rate_limit(BM.BlogPost, 'Create/edit', c.app.config.url())
        if delete:
            self.post.delete()
            flash('Post deleted', 'info')
            redirect(h.urlquote(h.really_unicode(c.app.url)))
        else:
            g.spam_checker.check(kw['title'] + '\n' + kw['text'], artifact=self.post,
                                 user=c.user, content_type='blog-post')
        attachment = kw.pop('attachment', None)
        old_text = self.post.text
        if attachment is not None:
            self.post.add_multiple_attachments(attachment)
        for k, val in kw.items():
            setattr(self.post, k, val)
        self.post.commit()
        notification_tasks.send_usermentions_notification.post(self.post.index_id(), kw['text'], old_text)
        redirect('.')

    @without_trailing_slash
    @expose('json:')
    @require_post()
    def update_markdown(self, text=None, **kw):
        if has_access(self.post, 'edit'):
            self.post.text = text
            self.post.commit()
            g.spam_checker.check(text, artifact=self.post,
                                 user=c.user, content_type='blog-post')
            return {
                'status': 'success'
            }
        else:
            return {
                'status': 'no_permission'
            }

    @expose()
    @without_trailing_slash
    def get_markdown(self):
        return self.post.text

    @without_trailing_slash
    @require_post()
    @expose('json:')
    def revert(self, version, **kw):
        require_access(self.post, 'write')
        orig = self._get_version(version)
        if orig:
            self.post.text = orig.text
        self.post.commit()
        return dict(location='.')

    @expose('json:')
    @require_post()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None, **kw):
        if subscribe:
            self.post.subscribe(type='direct')
        elif unsubscribe:
            self.post.unsubscribe()
        return {
            'status': 'ok',
            'subscribed': M.Mailbox.subscribed(artifact=self.post),
            'subscribed_to_tool': M.Mailbox.subscribed(),
        }

    def get_feed(self, project, app, user):
        """Return a :class:`allura.controllers.feed.FeedArgs` object describing
        the xml feed for this controller.

        Overrides :meth:`allura.controllers.feed.FeedController.get_feed`.

        """
        return FeedArgs(
            dict(ref_id=self.post.index_id()),
            'Recent changes to %s' % self.post.title,
            self.post.url())

    def _get_version(self, version):
        if not version:
            return self.post
        try:
            return self.post.get_version(version)
        except ValueError:
            raise exc.HTTPNotFound()


class BlogAdminController(DefaultAdminController):

    @without_trailing_slash
    @expose('jinja:forgeblog:templates/blog/admin_options.html')
    def options(self):
        return dict(app=self.app,
                    allow_config=has_access(self.app, 'configure')())

    @without_trailing_slash
    @expose()
    @require_post()
    def set_options(self, show_discussion=False, allow_email_posting=False):
        mount_point = self.app.config.options['mount_point']

        if self.app.config.options.get('show_discussion') != bool(show_discussion):
            M.AuditLog.log('{}: set option "{}" {} => {}'.format(
                mount_point, "show_discussion", self.app.config.options.get('show_discussion'),
                bool(show_discussion)))
            self.app.config.options['show_discussion'] = bool(show_discussion)

        if self.app.config.options.get('AllowEmailPosting') != bool(allow_email_posting):
            M.AuditLog.log('{}: set option "{}" {} => {}'.format(
                mount_point, "AllowEmailPosting", self.app.config.options.get('AllowEmailPosting'),
                bool(allow_email_posting)))
            self.app.config.options['AllowEmailPosting'] = bool(allow_email_posting)

        flash('Blog options updated')
        redirect(six.ensure_text(request.referer or '/'))

    @without_trailing_slash
    @expose('jinja:forgeblog:templates/blog/admin_exfeed.html')
    def exfeed(self):
        feeds_list = []
        for feed in self.app.external_feeds_list:
            feeds_list.append(feed)
        return dict(app=self.app,
                    feeds_list=feeds_list,
                    allow_config=has_access(self.app, 'configure')())

    @without_trailing_slash
    @expose()
    @require_post()
    def set_exfeed(self, new_exfeed=None, **kw):
        exfeed_val = kw.get('exfeed', [])
        if isinstance(exfeed_val, str):
            tmp_exfeed_list = []
            tmp_exfeed_list.append(exfeed_val)
        else:
            tmp_exfeed_list = exfeed_val

        if new_exfeed is not None and new_exfeed != '':
            tmp_exfeed_list.append(new_exfeed)

        exfeed_list = []
        invalid_list = []
        v = validators.URL()
        for link in tmp_exfeed_list:
            try:
                v.to_python(link)
                exfeed_list.append(link)
            except formencode.api.Invalid:
                invalid_list.append(link)

        added_feeds = set(exfeed_list).difference(self.app.external_feeds_list)
        removed_feeds = set(self.app.external_feeds_list).difference(exfeed_list)

        if added_feeds:
            M.AuditLog.log('{}: external feed list - added: {}'.format(
                self.app.config.options['mount_point'],
                ', '.join(sorted(added_feeds))
            ))
        if removed_feeds:
            M.AuditLog.log('{}: external feed list - removed: {}'.format(
                self.app.config.options['mount_point'],
                ', '.join(sorted(removed_feeds))
            ))

        self.app.external_feeds_list = exfeed_list
        flash('External feeds updated')
        if len(invalid_list) > 0:
            flash('Invalid link(s): %s' %
                  ','.join(link for link in invalid_list), 'error')

        redirect(six.ensure_text(request.referer or '/'))


class RootRestController(BaseController, AppRestControllerMixin):

    def __init__(self):
        self._discuss = AppDiscussionRestController()

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('json:')
    def index(self, title='', text='', state='draft', labels='', limit=10, page=0, **kw):
        if request.method == 'POST':
            require_access(c.app, 'write')
            if BM.BlogPost.is_limit_exceeded(c.app.config, user=c.user):
                log.warn('Create/edit rate limit exceeded. %s', c.app.config.url())
                raise forge_exc.HTTPTooManyRequests()
            post = BM.BlogPost.new(
                title=title,
                state=state,
                text=text,
                labels=labels.split(','),
                **kw)
            return exc.HTTPCreated(headers=dict(Location=str(h.absurl('/rest' + post.url()))))

        else:
            result = RootController().index(limit=limit, page=page)
            posts = result['posts']
            post_titles = []
            for post in posts:
                if has_access(post, 'read')():
                    post_titles.append(
                        {'title': post.title, 'url': h.absurl('/rest' + post.url())})
            return dict(posts=post_titles, count=result['count'], limit=result['limit'], page=result['page'])

    @expose()
    def _lookup(self, year=None, month=None, title=None, *rest):
        if not (year and month and title):
            raise exc.HTTPNotFound()
        slug = '/'.join((year, month, six.ensure_text(six.moves.urllib.parse.unquote(title))))
        post = BM.BlogPost.query.get(slug=slug, app_config_id=c.app.config._id)
        if not post:
            raise exc.HTTPNotFound()
        return PostRestController(post), rest


class PostRestController(BaseController):

    def __init__(self, post):
        self.post = post

    def _check_security(self):
        if self.post:
            require_access(self.post, 'read')

    @h.vardec
    @expose('json:')
    def index(self, **kw):
        if request.method == 'POST':
            return self._update_post(**kw)
        else:
            if self.post.state == 'draft':
                require_access(self.post, 'write')
            return self.post.__json__(posts_limit=10)

    def _update_post(self, **post_data):
        require_access(self.post, 'write')
        if BM.BlogPost.is_limit_exceeded(c.app.config, user=c.user):
            log.warn('Create/edit rate limit exceeded. %s', c.app.config.url())
            raise forge_exc.HTTPTooManyRequests()
        if 'delete' in post_data:
            self.post.delete()
            return {}
        if 'title' in post_data:
            self.post.title = post_data['title']
        if 'text' in post_data:
            self.post.text = post_data['text']
        if 'state' in post_data:
            self.post.state = post_data['state']
        if 'labels' in post_data:
            self.post.labels = post_data['labels'].split(',')
        self.post.commit()
        return self.post.__json__(posts_limit=10)
