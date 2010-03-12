from mimetypes import guess_type

from tg import expose, redirect, validate, request, response, flash
from tg.decorators import before_validate
from pylons import c
from webob import exc

from ming.base import Object
from ming.utils import LazyProperty

from pyforge import model as model
from pyforge.lib import helpers as h
from pyforge.lib.security import require, has_artifact_access

from pyforge.lib.widgets import discuss as DW

class pass_validator(object):
    def validate(self, v, s):
        return v
pass_validator=pass_validator()

class ModelConfig(object):
    Discussion=model.Discussion
    Thread=model.Thread
    Post=model.Post
    Attachment=model.Attachment

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
class DiscussionController(object):
    M=ModelConfig
    W=WidgetConfig

    def __init__(self):
        self.thread = ThreadsController(self)
        self.attachment = AttachmentsController(self)
        self.moderate = ModerationController(self)
        if not hasattr(self, 'ThreadController'):
            self.ThreadController = ThreadController
        if not hasattr(self, 'PostController'):
            self.PostController = PostController
        if not hasattr(self, 'AttachmentController'):
            self.AttachmentController = AttachmentController

    @expose('pyforge.templates.discussion.index')
    def index(self, **kw):
        c.discussion = self.W.discussion
        return dict(discussion=self.discussion)

    @h.vardec
    @expose()
    @validate(pass_validator, error_handler=index)
    def subscribe(self, **kw):
        kw = self.W.subscription_form.validate(kw, None)
        threads = kw.pop('threads')
        for t in threads:
            thread = t['_id']
            thread['subscription'] = t['subscription']
        redirect(request.referer)

class AppDiscussionController(DiscussionController):

    @LazyProperty
    def discussion(self):
        return self.M.Discussion.query.get(shortname=c.app.config.options.mount_point)

class ThreadsController(object):
    __metaclass__=h.ProxiedAttrMeta
    M=h.attrproxy('_discussion_controller', 'M')
    W=h.attrproxy('_discussion_controller', 'W')
    ThreadController=h.attrproxy('_discussion_controller', 'ThreadController')
    PostController=h.attrproxy('_discussion_controller', 'PostController')
    AttachmentController=h.attrproxy('_discussion_controller', 'AttachmentController')

    def __init__(self, discussion_controller):
        self._discussion_controller = discussion_controller

    @expose()
    def _lookup(self, id, *remainder):
        return self.ThreadController(self._discussion_controller, id), remainder

class ThreadController(object):
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
        return self.PostController(self._discussion_controller, self.thread, id), remainder

    @expose('pyforge.templates.discussion.thread')
    def index(self, offset=None, **kw):
        c.thread = self.W.thread
        c.thread_header = self.W.thread_header
        pagesize = 15
        if offset is None: offset = 0
        offset = int(offset)
        self.thread.num_views += 1
        return dict(discussion=self.thread.discussion,
                    thread=self.thread,
                    offset=offset,
                    total=self.thread.num_replies,
                    pagesize=pagesize)

    @h.vardec
    @expose()
    @validate(pass_validator, error_handler=index)
    def post(self, **kw):
        kw = self.W.edit_post.validate(kw, None)
        p = self.thread.post(**kw)
        p.commit()
        self.thread.num_replies += 1
        flash('Message posted')
        redirect(request.referer)

class PostController(object):
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

    @LazyProperty
    def post(self):
        result = self.M.Post.query.find(dict(slug=self._post_slug)).all()
        for p in result:
            if p.thread_id == self.thread._id: return p
        if result:
            redirect(result[0].url())

    @h.vardec
    @expose('pyforge.templates.discussion.post')
    @validate(pass_validator)
    def index(self, version=None, **kw):
        if self.post is None:
            redirect('..')
        c.post = self.W.post
        if request.method == 'POST':
            require(has_artifact_access('moderate', self.post))
            post_fields = self.W.edit_post.validate(kw, None)
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
                    reply_text=self.post.reply_text,
                    attachments=self.post.attachments,
                    )
            else:
                post=self.post
            return dict(discussion=self.post.discussion,
                        post=post)

    @h.vardec
    @expose()
    @validate(pass_validator, error_handler=index)
    def reply(self, **kw):
        require(has_artifact_access('post', self.thread))
        kw = self.W.edit_post.validate(kw, None)
        self.thread.post(parent_id=self.post._id, **kw)
        self.thread.num_replies += 1
        redirect(request.referer)

    @h.vardec
    @expose()
    @validate(pass_validator, error_handler=index)
    def moderate(self, **kw):
        require(has_artifact_access('moderate', self.post.thread))
        kw = self.W.moderate_post.validate(kw, None)
        if kw.pop('delete', None):
            self.post.delete()
            self.thread.update_stats()
        elif kw.pop('spam', None):
            self.post.status = 'spam'
            self.thread.update_stats()
        redirect(request.referer)

    @h.vardec
    @expose()
    @validate(pass_validator, error_handler=index)
    def flag(self, **kw):
        self.W.flag_post.validate(kw, None)
        if c.user._id not in self.post.flagged_by:
            self.post.flagged_by.append(c.user._id)
            self.post.flags += 1
        redirect(request.referer)

    @h.vardec
    @expose()
    def attach(self, file_info=None):
        require(has_artifact_access('moderate', self.post))
        filename = file_info.filename
        content_type = guess_type(filename)
        if content_type[0]: content_type = content_type[0]
        else: content_type = 'application/octet-stream'
        with self.M.Attachment.create(
            content_type=content_type,
            filename=filename,
            discussion_id=self.post.discussion._id,
            post_id=self.post._id) as fp:
            while True:
                s = file_info.file.read()
                if not s: break
                fp.write(s)
        redirect(request.referer)

    @expose()
    def _lookup(self, id, *remainder):
        return self.PostController(
            self._discussion_controller,
            self.thread, self._post_slug + '/' + id), remainder

class AttachmentsController(object):
    __metaclass__=h.ProxiedAttrMeta
    M=h.attrproxy('_discussion_controller', 'M')
    W=h.attrproxy('_discussion_controller', 'W')
    ThreadController=h.attrproxy('_discussion_controller', 'ThreadController')
    PostController=h.attrproxy('_discussion_controller', 'PostController')
    AttachmentController=h.attrproxy('_discussion_controller', 'AttachmentController')


    def __init__(self, discussion_controller):
        self._discussion_controller = discussion_controller

    @expose()
    def _lookup(self, filename, *args):
        return self.AttachmentController(self._discussion_controller, filename), args

class AttachmentController(object):
    __metaclass__=h.ProxiedAttrMeta
    M=h.attrproxy('_discussion_controller', 'M')
    W=h.attrproxy('_discussion_controller', 'W')
    ThreadController=h.attrproxy('_discussion_controller', 'ThreadController')
    PostController=h.attrproxy('_discussion_controller', 'PostController')
    AttachmentController=h.attrproxy('_discussion_controller', 'AttachmentController')

    def _check_security(self):
        require(has_artifact_access('read', self.post))

    def __init__(self, discussion_controller, filename):
        self._discussion_controller = discussion_controller
        self.filename = filename
        self.attachment = self.M.Attachment.query.get(filename=filename)
        self.post = self.attachment.post

    @expose()
    def index(self, delete=False, embed=False):
        if request.method == 'POST':
            require(has_artifact_access('moderate', self.post))
            if delete: self.attachment.delete()
            redirect(request.referer)
        with self.attachment.open() as fp:
            filename = fp.metadata['filename']
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type
            if not embed:
                response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()


class ModerationController(object):
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
    @expose('pyforge.templates.discussion.moderate')
    @validate(pass_validator)
    def index(self, **kw):
        kw = self.W.post_filter.validate(kw, None)
        offset = kw.pop('offset', 0)
        limit = kw.pop('limit', 50)
        status = kw.pop('status', '-')
        flag = kw.pop('flag', None)
        c.post_filter = self.W.post_filter
        c.moderate_posts = self.W.moderate_posts
        query = dict(
            discussion_id=self.discussion._id)
        if status != '-':
            query['status'] = status
        if flag:
            query['flags'] = {'$gte': int(flag) }
        q = self.M.Post.query.find(query)
        count = q.count()
        offset = int(offset)
        limit = int(limit)
        q = q.skip(offset)
        q = q.limit(limit)
        pgnum = (offset // limit) + 1
        pages = (count // limit) + 1
        return dict(discussion=self.discussion,
                    posts=q, offset=offset, limit=limit,
                    status=status, flag=flag,
                    pgnum=pgnum, pages=pages)

    @h.vardec
    @expose()
    def moderate(self, post=None,
                 approve=None,
                 spam=None,
                 delete=None,
                 **kw):
        for args in post:
            if not args.get('checked', False): continue
            post = self.M.Post.query.get(slug=args['slug'])
            if approve:
                if post.status != 'ok': post.approve()
            elif spam:
                if post.status != 'spam': post.spam()
            elif delete:
                post.delete()
        redirect(request.referer)

