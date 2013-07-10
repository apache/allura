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

#-*- python -*-
import logging
from datetime import datetime
import urllib2

# Non-stdlib imports
import pymongo
from tg import config, expose, validate, redirect, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import tmpl_context as c, app_globals as g
from pylons import request, response
from paste.deploy.converters import asbool
import formencode
from formencode import validators
from webob import exc
from urllib import unquote

from ming.orm import session

# Pyforge-specific imports
from allura.app import Application, SitemapEntry
from allura.app import DefaultAdminController
from allura.lib import helpers as h
from allura.lib.search import search_app
from allura.lib.decorators import require_post, Property
from allura.lib.security import has_access, require_access
from allura.lib import widgets as w
from allura.lib.widgets.subscriptions import SubscribeForm
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets.search import SearchResults, SearchHelp
from allura import model as M
from allura.controllers import BaseController, AppDiscussionController, AppDiscussionRestController
from allura.controllers.feed import FeedArgs, FeedController

# Local imports
from forgeblog import model as BM
from forgeblog import version
from forgeblog import widgets

log = logging.getLogger(__name__)

class W:
    thread=w.Thread(
        page=None, limit=None, page_size=None, count=None,
        style='linear')
    pager = widgets.BlogPager()
    new_post_form = widgets.NewPostForm()
    edit_post_form = widgets.EditPostForm()
    view_post_form = widgets.ViewPostForm()
    label_edit = ffw.LabelEdit()
    attachment_add = ffw.AttachmentAdd()
    attachment_list = ffw.AttachmentList()
    preview_post_form = widgets.PreviewPostForm()
    subscribe_form = SubscribeForm()
    search_results = SearchResults()
    help_modal = SearchHelp()

class ForgeBlogApp(Application):
    __version__ = version.__version__
    tool_label='Blog'
    tool_description="""
        Share exciting news and progress updates with your
        community.
    """
    default_mount_label='Blog'
    default_mount_point='blog'
    permissions = ['configure', 'read', 'write',
                    'unmoderated_post', 'post', 'moderate', 'admin']
    permissions_desc = {
        'read': 'View blog entries.',
        'write': 'Create new blog entry.',
        'admin': 'Set permissions. Enable/disable commenting.',
    }
    ordinal=14
    installable=True
    config_options = Application.config_options
    default_external_feeds = []
    icons={
        24:'images/blog_24.png',
        32:'images/blog_32.png',
        48:'images/blog_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = BlogAdminController(self)
        self.api_root = RootRestController()

    @Property
    def external_feeds_list():
        def fget(self):
            globals = BM.Globals.query.get(app_config_id=self.config._id)
            if globals is not None:
                external_feeds = globals.external_feeds
            else:
                external_feeds = self.default_external_feeds
            return external_feeds
        def fset(self, new_external_feeds):
            globals = BM.Globals.query.get(app_config_id=self.config._id)
            if globals is not None:
                globals.external_feeds = new_external_feeds
            elif len(new_external_feeds) > 0:
                globals = BM.Globals(app_config_id=self.config._id, external_feeds=new_external_feeds)
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
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    @property
    def show_discussion(self):
        if 'show_discussion' in self.config.options:
            return self.config.options['show_discussion']
        else:
            return True

    @h.exceptionless([], log)
    def sidebar_menu(self):
        base = c.app.url
        links = [
            SitemapEntry('Home', base),
            SitemapEntry('Search', base + 'search'),
            ]
        if has_access(self, 'write')():
            links += [ SitemapEntry('New Post', base + 'new') ]
        return links

    def admin_menu(self):
        import sys
        admin_url = c.project.url() + 'admin/' + self.config.options.mount_point + '/'
        # temporarily disabled until some bugs are fixed
        links = super(ForgeBlogApp, self).admin_menu(force_options=True)
        # We don't want external feeds in menu unless they're enabled
        if asbool(config.get('forgeblog.exfeed', 'false')):
            links.insert(0, SitemapEntry('External feeds', admin_url + 'exfeed', className='admin_modal'))
        return links
        #return super(ForgeBlogApp, self).admin_menu(force_options=True)

    def install(self, project):
        'Set up any default permissions and roles here'
        super(ForgeBlogApp, self).install(project)

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
        BM.Attachment.query.remove(dict(app_config_id=c.app.config._id))
        BM.BlogPost.query.remove(dict(app_config_id=c.app.config._id))
        BM.BlogPostSnapshot.query.remove(dict(app_config_id=c.app.config._id))
        super(ForgeBlogApp, self).uninstall(project)

class RootController(BaseController, FeedController):

    def __init__(self):
        self._discuss = AppDiscussionController()

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('jinja:forgeblog:templates/blog/index.html')
    @with_trailing_slash
    def index(self, page=0, limit=10, **kw):
        query_filter = dict(app_config_id=c.app.config._id)
        if not has_access(c.app, 'write')():
            query_filter['state'] = 'published'
        q = BM.BlogPost.query.find(query_filter)
        post_count = q.count()
        limit, page = h.paging_sanitizer(limit, page, post_count)
        posts = q.sort('timestamp', pymongo.DESCENDING) \
                 .skip(page * limit).limit(limit)
        c.form = W.preview_post_form
        c.pager = W.pager
        return dict(posts=posts, page=page, limit=limit, count=post_count)

    @with_trailing_slash
    @expose('jinja:forgeblog:templates/blog/search.html')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
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
        now = datetime.utcnow()
        post = dict(
            state='published')
        c.form = W.new_post_form
        return dict(post=post)

    @expose()
    @require_post()
    @validate(form=W.edit_post_form, error_handler=new)
    @without_trailing_slash
    def save(self, **kw):
        require_access(c.app, 'write')
        post = BM.BlogPost()
        for k,v in kw.iteritems():
            setattr(post, k, v)
        post.neighborhood_id=c.project.neighborhood_id
        post.make_slug()
        post.commit()
        M.Thread.new(discussion_id=post.app_config.discussion_id,
               ref_id=post.index_id(),
               subject='%s discussion' % post.title)
        redirect(h.really_unicode(post.url()).encode('utf-8'))


    @with_trailing_slash
    @expose('jinja:allura:templates/markdown_syntax_dialog.html')
    def markdown_syntax_dialog(self, **kw):
        'Static dialog page about how to use markdown.'
        return dict()

    @expose()
    def _lookup(self, year=None, month=None, name=None, *rest):
        if year is None or month is None or name is None:
            raise exc.HTTPNotFound()
        slug = '/'.join((year, month, urllib2.unquote(name).decode('utf-8')))
        post = BM.BlogPost.query.get(slug=slug, app_config_id=c.app.config._id)
        if post is None:
            raise exc.HTTPNotFound()
        return PostController(post), rest

class PostController(BaseController, FeedController):

    def __init__(self, post):
        self.post = post

    def _check_security(self):
        require_access(self.post, 'read')

    @expose('jinja:forgeblog:templates/blog/post.html')
    @with_trailing_slash
    @validate(dict(page=validators.Int(if_empty=0),
                   limit=validators.Int(if_empty=25)))
    def index(self, page=0, limit=25, **kw):
        if self.post.state == 'draft':
            require_access(self.post, 'write')
        c.form = W.view_post_form
        c.subscribe_form = W.subscribe_form
        c.thread = W.thread
        post_count = self.post.discussion_thread.post_count
        limit, page = h.paging_sanitizer(limit, page, post_count)
        version = kw.pop('version', None)
        post = self._get_version(version)
        base_post = self.post
        return dict(post=post, base_post=base_post,
                    page=page, limit=limit, count=post_count)

    @expose('jinja:forgeblog:templates/blog/edit_post.html')
    @without_trailing_slash
    def edit(self, **kw):
        require_access(self.post, 'write')
        c.form = W.edit_post_form
        c.attachment_add = W.attachment_add
        c.attachment_list = W.attachment_list
        c.label_edit = W.label_edit
        return dict(post=self.post)

    @without_trailing_slash
    @expose('jinja:forgeblog:templates/blog/post_history.html')
    def history(self, **kw):
        posts = self.post.history()
        return dict(title=self.post.title, posts=posts)

    @without_trailing_slash
    @expose('jinja:forgeblog:templates/blog/post_diff.html')
    def diff(self, v1, v2, **kw):
        p1 = self._get_version(int(v1))
        p2 = self._get_version(int(v2))
        result = h.diff_text(p1.text, p2.text)
        return dict(p1=p1, p2=p2, edits=result)

    @expose()
    @require_post()
    @validate(form=W.edit_post_form, error_handler=edit)
    @without_trailing_slash
    def save(self, delete=None, **kw):
        require_access(self.post, 'write')
        if delete:
            self.post.delete()
            flash('Post deleted', 'info')
            redirect(h.really_unicode(c.app.url).encode('utf-8'))
        for k,v in kw.iteritems():
            setattr(self.post, k, v)
        self.post.commit()
        redirect('.')

    @without_trailing_slash
    @require_post()
    @expose()
    def revert(self, version, **kw):
        require_access(self.post, 'write')
        orig = self._get_version(version)
        if orig:
            self.post.text = orig.text
        self.post.commit()
        redirect('.')

    @expose()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None, **kw):
        if subscribe:
            self.post.subscribe(type='direct')
        elif unsubscribe:
            self.post.unsubscribe()
        redirect(h.really_unicode(request.referer).encode('utf-8'))

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
        if not version: return self.post
        try:
            return self.post.get_version(version)
        except ValueError:
            raise exc.HTTPNotFound()

class BlogAdminController(DefaultAdminController):
    def __init__(self, app):
        self.app = app

    @without_trailing_slash
    @expose('jinja:forgeblog:templates/blog/admin_options.html')
    def options(self):
        return dict(app=self.app,
                    allow_config=has_access(self.app, 'configure')())

    @without_trailing_slash
    @expose()
    @require_post()
    def set_options(self, show_discussion=False):
        self.app.config.options['show_discussion'] = show_discussion and True or False
        flash('Blog options updated')
        redirect(h.really_unicode(c.project.url()+'admin/tools').encode('utf-8'))

    @without_trailing_slash
    @expose('jinja:forgeblog:templates/blog/admin_exfeed.html')
    def exfeed(self):
        #self.app.external_feeds_list = ['feed1', 'feed2']
        #log.info("EXFEED: %s" % self.app.external_feeds_list)
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
        if type(exfeed_val) == unicode:
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

        self.app.external_feeds_list = exfeed_list
        flash('External feeds updated')
        if len(invalid_list) > 0:
            flash('Invalid link(s): %s' % ','.join(link for link in invalid_list), 'error')

        redirect(c.project.url()+'admin/tools')


class RootRestController(BaseController):
    def __init__(self):
        self._discuss = AppDiscussionRestController()

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('json:')
    def index(self, title='', text='', state='draft', labels='', **kw):
        if request.method == 'POST':
            require_access(c.app, 'write')
            post = BM.BlogPost()
            post.title = title
            post.state = state
            post.text = text
            post.labels = labels.split(',')
            post.neighborhood_id = c.project.neighborhood_id
            post.make_slug()
            M.Thread.new(discussion_id=post.app_config.discussion_id,
                         ref_id=post.index_id(),
                         subject='%s discussion' % post.title)

            post.viewable_by = ['all']
            post.commit()
            return post.__json__()
        else:
            post_titles = []
            query_filter = dict(app_config_id=c.app.config._id, deleted=False)
            if not has_access(c.app, 'write')():
                query_filter['state'] = 'published'
            posts = BM.BlogPost.query.find(query_filter)
            for post in posts:
                if has_access(post, 'read')():
                    post_titles.append({'title': post.title, 'url': h.absurl('/rest' + post.url())})
            return dict(posts=post_titles)

    @expose()
    def _lookup(self, year=None, month=None, title=None, *rest):
        if not (year and month and title):
            raise exc.HTTPNotFound()
        slug = '/'.join((year, month, urllib2.unquote(title).decode('utf-8')))
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
            return self.post.__json__()

    def _update_post(self, **post_data):
        require_access(self.post, 'write')
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
        return self.post.__json__()