#-*- python -*-
import logging
from datetime import datetime

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, session
from tg.decorators import with_trailing_slash, without_trailing_slash
from tg import g, c, request, response
from formencode import validators
from webob import exc

# Pyforge-specific imports
from allura.app import Application, ConfigOption, SitemapEntry
from allura.lib import helpers as h
from allura.lib.search import search
from allura.lib.decorators import require_post
from allura.lib.security import has_access, require_access
from allura.lib import widgets as w
from allura.lib.widgets.subscriptions import SubscribeForm
from allura.lib.widgets import form_fields as ffw
from allura import model as M
from allura.controllers import BaseController, AppDiscussionController

# Local imports
from forgeblog import model as BM
from forgeblog import version
from forgeblog import widgets

log = logging.getLogger(__name__)

class W:
    thread=w.Thread(
        page=None, limit=None, page_size=None, count=None,
        style='linear')
    new_post_form = widgets.NewPostForm()
    edit_post_form = widgets.EditPostForm()
    view_post_form = widgets.ViewPostForm()
    label_edit = ffw.LabelEdit()
    attachment_add = ffw.AttachmentAdd()
    attachment_list = ffw.AttachmentList()
    preview_post_form = widgets.PreviewPostForm()
    subscribe_form = SubscribeForm()

class ForgeBlogApp(Application):
    __version__ = version.__version__
    tool_label='Blog'
    status='alpha'
    default_mount_label='Blog'
    default_mount_point='blog'
    permissions = ['configure', 'read', 'write',
                    'unmoderated_post', 'post', 'moderate', 'admin']
    ordinal=14
    installable=True
    config_options = Application.config_options
    show_discussion=True
    icons={
        24:'allura/images/blog_24.png',
        32:'allura/images/blog_32.png',
        48:'allura/images/blog_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

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
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = []
        if self.permissions and has_access(self, 'configure', app=self)():
            links.append(SitemapEntry('Permissions', admin_url + 'permissions', className='nav_child'))
        return links

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
            M.ACE.allow(role_anon, 'post'),
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

class RootController(BaseController):

    def __init__(self):
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)
        self._discuss = AppDiscussionController()

    @expose('jinja:forgeblog:templates/blog/index.html')
    @with_trailing_slash
    def index(self, **kw):
        if has_access(c.app, 'write')():
            posts = BM.BlogPost.query.find(dict(
                    app_config_id=c.app.config._id)).sort('-timestamp')
        else:
            posts = BM.BlogPost.query.find(dict(
                        state='published',
                        app_config_id=c.app.config._id)).sort('-timestamp')
        c.form = W.preview_post_form
        return dict(posts=posts)

    @expose('jinja:forgeblog:templates/blog/search.html')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None, **kw):
        'local tool search'
        results = []
        count=0
        if not q:
            q = ''
        else:
            results = search(
                q,
                fq=[
                    'state_s:published',
                    'is_history_b:%s' % history,
                    'project_id_s:%s' % c.project._id,
                    'mount_point_s:%s'% c.app.config.options.mount_point ])
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

    @expose('jinja:forgeblog:templates/blog/edit_post.html')
    @without_trailing_slash
    def new(self, **kw):
        require_access(c.app, 'write')
        now = datetime.utcnow()
        post = dict(
            title='Please enter a title',
            text='Type your text here',
            date=now.date(),
            time=now.time(),
            state='draft')
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
        post.make_slug()
        post.commit()
        M.Thread(discussion_id=post.app_config.discussion_id,
               ref_id=post.index_id(),
               subject='%s discussion' % post.title)
        redirect(post.url())


    @without_trailing_slash
    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None, if_invalid=None),
            until=h.DateTimeConverter(if_empty=None, if_invalid=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, offset=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent changes to %s' % c.app.config.options.mount_point
        feed = M.Feed.feed(
            dict(project_id=c.project._id, app_config_id=c.app.config._id),
            feed_type,
            title,
            c.app.url,
            title,
            since, until, offset, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')
    @expose()
    def _lookup(self, year, month, name, *rest):
        slug = '/'.join((year, month, name))
        post = BM.BlogPost.query.get(slug=slug)
        if post is None:
            raise exc.HTTPNotFound()
        return PostController(post), rest

class PostController(BaseController):

    def __init__(self, post):
        self.post = post
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)

    def _check_security(self):
        require_access(self.post, 'read')

    @expose('jinja:forgeblog:templates/blog/post.html')
    @with_trailing_slash
    def index(self, **kw):
        c.form = W.view_post_form
        c.subscribe_form = W.subscribe_form
        c.thread = W.thread
        version = kw.pop('version', None)
        post = self._get_version(version)
        base_post = self.post
        return dict(post=post, base_post=base_post)

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
    def history(self):
        posts = self.post.history()
        return dict(title=self.post.title, posts=posts)

    @without_trailing_slash
    @expose('jinja:forgeblog:templates/blog/post_diff.html')
    def diff(self, v1, v2):
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
            session.flash('Post deleted', 'info')
            redirect(c.app.url)
        for k,v in kw.iteritems():
            setattr(self.post, k, v)
        self.post.commit()
        redirect('.')

    @without_trailing_slash
    @require_post()
    @expose()
    def revert(self, version):
        require_access(self.post, 'write')
        orig = self._get_version(version)
        if orig:
            self.post.text = orig.text
        self.post.commit()
        redirect('.')

    @expose()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None):
        if subscribe:
            self.post.subscribe(type='direct')
        elif unsubscribe:
            self.post.unsubscribe()
        redirect(request.referer)

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None, if_invalid=None),
            until=h.DateTimeConverter(if_empty=None, if_invalid=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, offset=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        feed = M.Feed.feed(
            dict(ref_id=self.post.index_id()),
            feed_type,
            'Recent changes to %s' % self.post.title,
            self.post.url(),
            'Recent changes to %s' % self.post.title,
            since, until, offset, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

    def _get_version(self, version):
        if not version: return self.post
        try:
            return self.post.get_version(version)
        except ValueError:
            raise exc.HTTPNotFound()
