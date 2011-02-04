from urllib import unquote
from datetime import datetime

from tg import expose, redirect, validate, request, response, flash
from tg.decorators import before_validate, with_trailing_slash, without_trailing_slash
from pylons import g, c
from formencode import validators
from webob import exc

from ming.base import Object
from ming.utils import LazyProperty

from allura import model as M
from base import BaseController
from allura.lib import utils
from allura.lib import helpers as h
from allura.lib.decorators import require_post
from allura.lib.security import require, has_artifact_access
from allura.lib.helpers import DateTimeConverter

from allura.lib.widgets import discuss as DW
from .attachments import AttachmentsController, AttachmentController

class pass_validator(object):
    def validate(self, v, s):
        return v
pass_validator=pass_validator()

class ModelConfig(object):
    Discussion=M.Discussion
    Thread=M.Thread
    Post=M.Post
    Attachment=M.DiscussionAttachment

class WidgetConfig(object):
    # Forms
    subscription_form = DW.SubscriptionForm()
    edit_post = DW.EditPost()
    moderate_thread = DW.ModerateThread()
    moderate_post = DW.ModeratePost()
    flag_post = DW.FlagPost()
    post_filter = DW.PostFilter()
    moderate_posts=DW.ModeratePosts()
    # Other widgets
    discussion = DW.Discussion()
    thread = DW.Thread()
    post = DW.Post()
    thread_header = DW.ThreadHeader()

# Controllers
class DiscussionController(BaseController):
    M=ModelConfig
    W=WidgetConfig

    def __init__(self):
        if not hasattr(self, 'ThreadController'):
            self.ThreadController = ThreadController
        if not hasattr(self, 'PostController'):
            self.PostController = PostController
        if not hasattr(self, 'AttachmentController'):
            self.AttachmentController = DiscussionAttachmentController
        self.thread = ThreadsController(self)
        if not hasattr(self, 'moderate'):
            self.moderate = ModerationController(self)

    @expose('jinja:discussion/index.html')
    def index(self, threads=None, limit=None, page=0, count=0, **kw):
        c.discussion = self.W.discussion
        if threads is None:
            threads = self.discussion.threads
        return dict(discussion=self.discussion, limit=limit, page=page, count=count, threads=threads)

    @h.vardec
    @expose()
    @require_post()
    @validate(pass_validator, error_handler=index)
    def subscribe(self, **kw):
        threads = kw.pop('threads')
        for t in threads:
            thread = self.M.Thread.query.find(dict(_id=t['_id'])).first()
            if 'subscription' in t:
                thread['subscription'] = True
            else:
                thread['subscription'] = False
            M.session.artifact_orm_session._get().skip_mod_date = True
        redirect(request.referer)

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(dict(
            since=DateTimeConverter(if_empty=None),
            until=DateTimeConverter(if_empty=None),
            page=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, page=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent posts to %s' % self.discussion.name
        feed = M.Feed.feed(
            {'artifact_reference':{'$in': [t.dump_ref() for t in self.discussion.threads]}},
            feed_type,
            title,
            self.discussion.url(),
            title,
            since, until, page, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

class AppDiscussionController(DiscussionController):

    @LazyProperty
    def discussion(self):
        return self.M.Discussion.query.get(shortname=c.app.config.options.mount_point,
                                           app_config_id=c.app.config._id)

class ThreadsController(BaseController):
    __metaclass__=h.ProxiedAttrMeta
    M=h.attrproxy('_discussion_controller', 'M')
    W=h.attrproxy('_discussion_controller', 'W')
    ThreadController=h.attrproxy('_discussion_controller', 'ThreadController')
    PostController=h.attrproxy('_discussion_controller', 'PostController')
    AttachmentController=h.attrproxy('_discussion_controller', 'AttachmentController')

    def __init__(self, discussion_controller):
        self._discussion_controller = discussion_controller

    @expose()
    def _lookup(self, id=None, *remainder):
        if id:
            id=unquote(id)
            return self.ThreadController(self._discussion_controller, id), remainder
        else:
            raise exc.HTTPNotFound()

class ThreadController(BaseController):
    __metaclass__=h.ProxiedAttrMeta
    M=h.attrproxy('_discussion_controller', 'M')
    W=h.attrproxy('_discussion_controller', 'W')
    ThreadController=h.attrproxy('_discussion_controller', 'ThreadController')
    PostController=h.attrproxy('_discussion_controller', 'PostController')
    AttachmentController=h.attrproxy('_discussion_controller', 'AttachmentController')

    def _check_security(self):
        require(has_artifact_access('read', self.thread))

    def __init__(self, discussion_controller, thread_id):
        self._discussion_controller = discussion_controller
        self.discussion = discussion_controller.discussion
        self.thread = self.M.Thread.query.get(_id=thread_id)

    @expose()
    def _lookup(self, id, *remainder):
        id=unquote(id)
        return self.PostController(self._discussion_controller, self.thread, id), remainder

    @expose('jinja:discussion/thread.html')
    def index(self, limit=None, page=0, count=0, **kw):
        c.thread = self.W.thread
        c.thread_header = self.W.thread_header
        limit, page, start = g.handle_paging(limit, page)
        self.thread.num_views += 1
        M.session.artifact_orm_session._get().skip_mod_date = True # the update to num_views shouldn't affect it
        count = self.thread.query_posts(page=page, limit=int(limit)).count()
        return dict(discussion=self.thread.discussion,
                    thread=self.thread,
                    page=page,
                    count=count,
                    limit=limit)

    @h.vardec
    @expose()
    @require_post()
    @validate(pass_validator, error_handler=index)
    def post(self, **kw):
        require(has_artifact_access('post', self.thread))
        kw = self.W.edit_post.to_python(kw, None)
        if not kw['text']:
            flash('Your post was not saved. You must provide content.', 'error')
            redirect(request.referer)
        file_info = kw.pop('file_info', None)
        p = self.thread.add_post(**kw)
        if hasattr(file_info, 'file'):
            p.attach(
                file_info.filename, file_info.file, content_type=file_info.type,
                post_id=p._id,
                thread_id=p.thread_id,
                discussion_id=p.discussion_id)
        if self.thread.artifact:
            self.thread.artifact.mod_date = datetime.utcnow()
        flash('Message posted')
        redirect(request.referer)

    @expose()
    @require_post()
    def tag(self, labels, **kw):
        require(has_artifact_access('post', self.thread))
        self.thread.labels = labels.split(',')
        redirect(request.referer)

    @expose()
    @require_post()
    def flag_as_spam(self, **kw):
        require(has_artifact_access('moderate', self.thread))
        self.thread.first_post.status='spam'
        flash('Thread flagged as spam.')
        redirect(request.referer)

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=DateTimeConverter(if_empty=None),
            until=DateTimeConverter(if_empty=None),
            page=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, page=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent posts to %s' % (self.thread.subject or '(no subject)')
        feed = M.Feed.feed(
            {'artifact_reference':self.thread.dump_ref()},
            feed_type,
            title,
            self.thread.url(),
            title,
            since, until, page, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

class PostController(BaseController):
    __metaclass__=h.ProxiedAttrMeta
    M=h.attrproxy('_discussion_controller', 'M')
    W=h.attrproxy('_discussion_controller', 'W')
    ThreadController=h.attrproxy('_discussion_controller', 'ThreadController')
    PostController=h.attrproxy('_discussion_controller', 'PostController')
    AttachmentController=h.attrproxy('_discussion_controller', 'AttachmentController')

    def _check_security(self):
        require(has_artifact_access('read', self.post))

    def __init__(self, discussion_controller, thread, slug):
        self._discussion_controller = discussion_controller
        self.thread = thread
        self._post_slug = slug
        self.attachment = DiscussionAttachmentsController(self.post)

    @LazyProperty
    def post(self):
        result = self.M.Post.query.find(dict(slug=self._post_slug)).all()
        for p in result:
            if p.thread_id == self.thread._id: return p
        if result:
            redirect(result[0].url())
        else:
            redirect('..')

    @h.vardec
    @expose('jinja:discussion/post.html')
    @validate(pass_validator)
    def index(self, version=None, **kw):
        c.post = self.W.post
        if request.method == 'POST':
            require(has_artifact_access('moderate', self.post))
            post_fields = self.W.edit_post.to_python(kw, None)
            file_info = post_fields.pop('file_info', None)
            if hasattr(file_info, 'file'):
                self.post.attach(
                    file_info.filename, file_info.file, content_type=file_info.type,
                    post_id=self.post._id,
                    thread_id=self.post.thread_id,
                    discussion_id=self.post.discussion_id)
            for k,v in post_fields.iteritems():
                try:
                    setattr(self.post, k, v)
                except AttributeError:
                    continue
            redirect(request.referer)
        elif request.method=='GET':
            if version is not None:
                HC = self.post.__mongometa__.history_class
                ss = HC.query.find({'artifact_id':self.post._id, 'version':int(version)}).first()
                if not ss: raise exc.HTTPNotFound
                post = Object(
                    ss.data,
                    acl=self.post.acl,
                    author=self.post.author,
                    url=self.post.url,
                    thread=self.post.thread,
                    reply_subject=self.post.reply_subject,
                    attachments=self.post.attachments,
                    )
            else:
                post=self.post
            return dict(discussion=self.post.discussion,
                        post=post)

    @h.vardec
    @expose()
    @require_post()
    @validate(pass_validator, error_handler=index)
    @require_post(redir='.')
    def reply(self, **kw):
        require(has_artifact_access('post', self.thread))
        kw = self.W.edit_post.to_python(kw, None)
        self.thread.post(parent_id=self.post._id, **kw)
        self.thread.num_replies += 1
        redirect(self.thread.url())

    @h.vardec
    @expose()
    @require_post()
    @validate(pass_validator, error_handler=index)
    def moderate(self, **kw):
        require(has_artifact_access('moderate', self.post.thread))
        if kw.pop('delete', None):
            self.post.delete()
            self.thread.update_stats()
        elif kw.pop('spam', None):
            self.post.status = 'spam'
            self.thread.update_stats()
        redirect(request.referer)

    @h.vardec
    @expose()
    @require_post()
    @validate(pass_validator, error_handler=index)
    def flag(self, **kw):
        self.W.flag_post.to_python(kw, None)
        if c.user._id not in self.post.flagged_by:
            self.post.flagged_by.append(c.user._id)
            self.post.flags += 1
        redirect(request.referer)

    @h.vardec
    @expose()
    @require_post()
    def attach(self, file_info=None):
        require(has_artifact_access('moderate', self.post))
        if hasattr(file_info, 'file'):
            mime_type = file_info.type
            # If mime type was not passed or bogus, guess it
            if not mime_type or '/' not in mime_type:
                mime_type = utils.guess_mime_type(file_info.filename)
            self.post.attach(
                file_info.filename, file_info.file, content_type=mime_type,
                post_id=self.post._id,
                thread_id=self.post.thread_id,
                discussion_id=self.post.discussion_id)
        redirect(request.referer)

    @expose()
    def _lookup(self, id, *remainder):
        id=unquote(id)
        return self.PostController(
            self._discussion_controller,
            self.thread, self._post_slug + '/' + id), remainder

class DiscussionAttachmentController(AttachmentController):
    AttachmentClass=M.DiscussionAttachment
    edit_perm='moderate'

class DiscussionAttachmentsController(AttachmentsController):
    AttachmentControllerClass=DiscussionAttachmentController

class ModerationController(BaseController):
    __metaclass__=h.ProxiedAttrMeta
    M=h.attrproxy('_discussion_controller', 'M')
    W=h.attrproxy('_discussion_controller', 'W')
    ThreadController=h.attrproxy('_discussion_controller', 'ThreadController')
    PostController=h.attrproxy('_discussion_controller', 'PostController')
    AttachmentController=h.attrproxy('_discussion_controller', 'AttachmentController')

    def _check_security(self):
        require(has_artifact_access('moderate', self.discussion))

    def __init__(self, discussion_controller):
        self._discussion_controller = discussion_controller

    @LazyProperty
    def discussion(self):
        return self._discussion_controller.discussion

    @h.vardec
    @expose('jinja:discussion/moderate.html')
    @validate(pass_validator)
    def index(self, **kw):
        kw = WidgetConfig.post_filter.to_python(kw, None)
        page = kw.pop('page', 0)
        limit = kw.pop('limit', 50)
        status = kw.pop('status', '-')
        flag = kw.pop('flag', None)
        c.post_filter = WidgetConfig.post_filter
        c.moderate_posts = WidgetConfig.moderate_posts
        query = dict(
            discussion_id=self.discussion._id)
        if status != '-':
            query['status'] = status
        if flag:
            query['flags'] = {'$gte': int(flag) }
        q = M.Post.query.find(query)
        count = q.count()
        page = int(page)
        limit = int(limit)
        q = q.skip(page)
        q = q.limit(limit)
        pgnum = (page // limit) + 1
        pages = (count // limit) + 1
        return dict(discussion=self.discussion,
                    posts=q, page=page, limit=limit,
                    status=status, flag=flag,
                    pgnum=pgnum, pages=pages)

    @h.vardec
    @expose()
    @require_post()
    def moderate(self, post=None,
                 approve=None,
                 spam=None,
                 delete=None,
                 **kw):
        for args in post:
            if not args.get('checked', False): continue
            post = M.Post.query.get(slug=args['slug'])
            if approve:
                if post.status != 'ok':
                    post.approve()
            elif spam:
                if post.status != 'spam': post.spam()
            elif delete:
                post.delete()
        redirect(request.referer)

class PostRestController(PostController):

    @expose('json:')
    def index(self, **kw):
        return dict(post=self.post)

    @h.vardec
    @expose()
    @require_post()
    @validate(pass_validator, error_handler=h.json_validation_error)
    def reply(self, **kw):
        require(has_artifact_access('post', self.thread))
        kw = self.W.edit_post.to_python(kw, None)
        post = self.thread.post(parent_id=self.post._id, **kw)
        self.thread.num_replies += 1
        redirect(post.slug.split('/')[-1] + '/')

class ThreadRestController(ThreadController):

    @expose('json:')
    def index(self, **kw):
        return dict(thread=self.thread)

    @h.vardec
    @expose()
    @require_post()
    @validate(pass_validator, error_handler=h.json_validation_error)
    def new(self, **kw):
        require(has_artifact_access('post', self.thread))
        kw = self.W.edit_post.to_python(kw, None)
        p = self.thread.add_post(**kw)
        redirect(p.slug + '/')

class AppDiscussionRestController(AppDiscussionController):
    ThreadController = ThreadRestController
    PostController = PostRestController

    @expose('json:')
    def index(self, **kw):
        return dict(discussion=self.discussion)
