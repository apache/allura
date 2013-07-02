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

from urllib import unquote
from datetime import datetime
import logging

from tg import expose, redirect, validate, request, response, flash
from tg.decorators import before_validate, with_trailing_slash, without_trailing_slash
from pylons import tmpl_context as c, app_globals as g
from formencode import validators
from webob import exc

from ming.base import Object
from ming.utils import LazyProperty

from allura import model as M
from base import BaseController
from allura.lib import utils
from allura.lib import helpers as h
from allura.lib.decorators import require_post
from allura.lib.security import require, has_access, require_access
from allura.lib.helpers import DateTimeConverter

from allura.lib.widgets import discuss as DW
from .attachments import AttachmentsController, AttachmentController
from .feed import FeedArgs, FeedController

log = logging.getLogger(__name__)

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
    discussion_header = DW.DiscussionHeader()

# Controllers
class DiscussionController(BaseController, FeedController):
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

    @expose('jinja:allura:templates/discussion/index.html')
    def index(self, threads=None, limit=None, page=0, count=0, **kw):
        c.discussion = self.W.discussion
        c.discussion_header = self.W.discussion_header
        if threads is None:
            threads = self.discussion.threads
        return dict(discussion=self.discussion, limit=limit, page=page, count=count, threads=threads)

    @h.vardec
    @expose()
    @validate(pass_validator, error_handler=index)
    def subscribe(self, **kw):
        threads = kw.pop('threads', [])
        for t in threads:
            thread = self.M.Thread.query.find(dict(_id=t['_id'])).first()
            if 'subscription' in t:
                thread['subscription'] = True
            else:
                thread['subscription'] = False
            M.session.artifact_orm_session._get().skip_mod_date = True
        redirect(request.referer)

    def get_feed(self, project, app, user):
        """Return a :class:`allura.controllers.feed.FeedArgs` object describing
        the xml feed for this controller.

        Overrides :meth:`allura.controllers.feed.FeedController.get_feed`.

        """
        return FeedArgs(
            dict(ref_id={'$in': [t.index_id() for t in self.discussion.threads]}),
            'Recent posts to %s' % self.discussion.name,
            self.discussion.url())


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

class ThreadController(BaseController, FeedController):
    __metaclass__=h.ProxiedAttrMeta
    M=h.attrproxy('_discussion_controller', 'M')
    W=h.attrproxy('_discussion_controller', 'W')
    ThreadController=h.attrproxy('_discussion_controller', 'ThreadController')
    PostController=h.attrproxy('_discussion_controller', 'PostController')
    AttachmentController=h.attrproxy('_discussion_controller', 'AttachmentController')

    def _check_security(self):
        require_access(self.thread, 'read')
        if self.thread.ref:
            require_access(self.thread.ref.artifact, 'read')

    def __init__(self, discussion_controller, thread_id):
        self._discussion_controller = discussion_controller
        self.discussion = discussion_controller.discussion
        self.thread = self.M.Thread.query.get(_id=thread_id)
        if not self.thread:
            raise exc.HTTPNotFound

    @expose()
    def _lookup(self, id, *remainder):
        id=unquote(id)
        return self.PostController(self._discussion_controller, self.thread, id), remainder

    @expose('jinja:allura:templates/discussion/thread.html')
    def index(self, limit=None, page=0, count=0, **kw):
        c.thread = self.W.thread
        c.thread_header = self.W.thread_header
        limit, page, start = g.handle_paging(limit, page)
        self.thread.num_views += 1
        M.session.artifact_orm_session._get().skip_mod_date = True # the update to num_views shouldn't affect it
        count = self.thread.query_posts(page=page, limit=int(limit)).count()
        return dict(discussion=self.thread.discussion,
                    thread=self.thread,
                    page=int(page),
                    count=int(count),
                    limit=int(limit),
                    show_moderate=kw.get('show_moderate'))

    @h.vardec
    @expose()
    @require_post()
    @validate(pass_validator, error_handler=index)
    @utils.AntiSpam.validate('Spambot protection engaged')
    def post(self, **kw):
        require_access(self.thread, 'post')
        if self.thread.ref:
            require_access(self.thread.ref.artifact, 'post')
        kw = self.W.edit_post.to_python(kw, None)
        if not kw['text']:
            flash('Your post was not saved. You must provide content.', 'error')
            redirect(request.referer)

        file_info = kw.get('file_info', None)
        p = self.thread.add_post(**kw)
        p.add_attachment(file_info)
        if self.thread.artifact:
            self.thread.artifact.mod_date = datetime.utcnow()
        flash('Message posted')
        redirect(request.referer)

    @expose()
    @require_post()
    def tag(self, labels, **kw):
        require_access(self.thread, 'post')
        if self.thread.ref:
            require_access(self.thread.ref.artifact, 'post')
        self.thread.labels = labels.split(',')
        redirect(request.referer)

    @expose()
    def flag_as_spam(self, **kw):
        require_access(self.thread, 'moderate')
        self.thread.spam()
        flash('Thread flagged as spam.')
        redirect(self.discussion.url())

    def get_feed(self, project, app, user):
        """Return a :class:`allura.controllers.feed.FeedArgs` object describing
        the xml feed for this controller.

        Overrides :meth:`allura.controllers.feed.FeedController.get_feed`.

        """
        return FeedArgs(
            dict(ref_id=self.thread.index_id()),
            'Recent posts to %s' % (self.thread.subject or '(no subject)'),
            self.thread.url())


class PostController(BaseController):
    __metaclass__=h.ProxiedAttrMeta
    M=h.attrproxy('_discussion_controller', 'M')
    W=h.attrproxy('_discussion_controller', 'W')
    ThreadController=h.attrproxy('_discussion_controller', 'ThreadController')
    PostController=h.attrproxy('_discussion_controller', 'PostController')
    AttachmentController=h.attrproxy('_discussion_controller', 'AttachmentController')

    def _check_security(self):
        require_access(self.post, 'read')

    def __init__(self, discussion_controller, thread, slug):
        self._discussion_controller = discussion_controller
        self.thread = thread
        self._post_slug = slug
        self.attachment = DiscussionAttachmentsController(self.post)

    @LazyProperty
    def post(self):
        post = self.M.Post.query.get(slug=self._post_slug, thread_id=self.thread._id)
        if post:
            return post
        post = self.M.Post.query.get(slug=self._post_slug)
        if post:
            return post
        else:
            redirect('..')

    @h.vardec
    @expose('jinja:allura:templates/discussion/post.html')
    @validate(pass_validator)
    @utils.AntiSpam.validate('Spambot protection engaged')
    def index(self, version=None, **kw):
        c.post = self.W.post
        if request.method == 'POST':
            require_access(self.post, 'moderate')
            post_fields = self.W.edit_post.to_python(kw, None)
            file_info = post_fields.pop('file_info', None)
            self.post.add_attachment(file_info)
            for k,v in post_fields.iteritems():
                try:
                    setattr(self.post, k, v)
                except AttributeError:
                    continue
            self.post.edit_count = self.post.edit_count + 1
            self.post.last_edit_date = datetime.utcnow()
            self.post.last_edit_by_id = c.user._id
            self.post.commit()
            g.director.create_activity(c.user, 'modified', self.post,
                    target=self.post.thread.artifact or self.post.thread,
                    related_nodes=[self.post.app_config.project])
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
                    related_artifacts=self.post.related_artifacts,
                    parent_security_context=lambda: None,
                    )
            else:
                post=self.post
            return dict(discussion=self.post.discussion,
                        post=post)

    @h.vardec
    @expose()
    @require_post()
    @validate(pass_validator, error_handler=index)
    @utils.AntiSpam.validate('Spambot protection engaged')
    @require_post(redir='.')
    def reply(self, file_info=None, **kw):
        require_access(self.thread, 'post')
        kw = self.W.edit_post.to_python(kw, None)
        p = self.thread.add_post(parent_id=self.post._id, **kw)
        p.add_attachment(file_info)
        redirect(request.referer)

    @h.vardec
    @expose()
    @require_post()
    @validate(pass_validator, error_handler=index)
    def moderate(self, **kw):
        require_access(self.post.thread, 'moderate')
        if kw.pop('delete', None):
            self.post.delete()
        elif kw.pop('spam', None):
            self.post.spam()
        elif kw.pop('approve', None):
            self.post.status = 'ok'
            g.spam_checker.submit_ham(self.post.text, artifact=self.post, user=c.user)
        self.thread.update_stats()
        return dict(result ='success')

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
        require_access(self.post, 'moderate')
        self.post.add_attachment(file_info)
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
    PostModel = M.Post
    M=h.attrproxy('_discussion_controller', 'M')
    W=h.attrproxy('_discussion_controller', 'W')
    ThreadController=h.attrproxy('_discussion_controller', 'ThreadController')
    PostController=h.attrproxy('_discussion_controller', 'PostController')
    AttachmentController=h.attrproxy('_discussion_controller', 'AttachmentController')

    def _check_security(self):
        require_access(self.discussion, 'moderate')

    def __init__(self, discussion_controller):
        self._discussion_controller = discussion_controller

    @LazyProperty
    def discussion(self):
        return self._discussion_controller.discussion

    @h.vardec
    @expose('jinja:allura:templates/discussion/moderate.html')
    @validate(pass_validator)
    def index(self, **kw):
        kw = WidgetConfig.post_filter.validate(kw, None)
        page = kw.pop('page', 0)
        limit = kw.pop('limit', 50)
        status = kw.pop('status', 'pending')
        flag = kw.pop('flag', None)
        c.post_filter = WidgetConfig.post_filter
        c.moderate_posts = WidgetConfig.moderate_posts
        query = dict(
            discussion_id=self.discussion._id)
        if status != '-':
            query['status'] = status
        if flag:
            query['flags'] = {'$gte': int(flag) }
        q = self.PostModel.query.find(query)
        count = q.count()
        if not page:
            page = 0
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
    def save_moderation(self, post=[], delete=None, spam=None, approve=None, **kw):
        for p in post:
            if 'checked' in p:
                posted = self.PostModel.query.get(full_slug=p['full_slug'])
                if posted:
                    if delete:
                        posted.delete()
                        # If we just deleted the last post in the
                        # thread, delete the thread.
                        if posted.thread and posted.thread.num_replies == 0:
                            posted.thread.delete()
                    elif spam and posted.status != 'spam':
                        posted.spam()
                    elif approve and posted.status != 'ok':
                        posted.status = 'ok'
                        g.spam_checker.submit_ham(posted.text, artifact=posted, user=c.user)
                        posted.thread.last_post_date = max(
                            posted.thread.last_post_date,
                            posted.mod_date)
                        posted.thread.num_replies += 1
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
        require_access(self.thread, 'post')
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
        require_access(self.thread, 'post')
        kw = self.W.edit_post.to_python(kw, None)
        p = self.thread.add_post(**kw)
        redirect(p.slug + '/')

class AppDiscussionRestController(AppDiscussionController):
    ThreadController = ThreadRestController
    PostController = PostRestController

    @expose('json:')
    def index(self, **kw):
        return dict(discussion=self.discussion)
