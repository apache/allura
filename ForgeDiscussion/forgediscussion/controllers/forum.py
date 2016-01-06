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
import pymongo

from tg import expose, validate, redirect
from tg import request
from pylons import tmpl_context as c, app_globals as g
from webob import exc
from formencode import validators

from allura.lib import helpers as h
from allura.lib import utils
from allura import model as M
from allura.lib.security import has_access, require_access
from allura.lib.decorators import require_post
from allura.controllers import DiscussionController, ThreadController, PostController, ModerationController
from allura.lib.widgets import discuss as DW
from allura.lib.widgets.subscriptions import SubscribeForm

from forgediscussion import model as DM
from forgediscussion import widgets as FW
from forgediscussion import tasks

log = logging.getLogger(__name__)


class pass_validator(object):

    def validate(self, v, s):
        return v
pass_validator = pass_validator()


class ModelConfig(object):
    Discussion = DM.Forum
    Thread = DM.ForumThread
    Post = DM.ForumPost
    Attachment = M.DiscussionAttachment


class WidgetConfig(object):
    # Forms
    subscription_form = DW.SubscriptionForm()
    subscribe_form = SubscribeForm()
    edit_post = DW.EditPost(show_subject=True)
    moderate_thread = FW.ModerateThread()
    post_filter = DW.PostFilter()
    moderate_posts = DW.ModeratePosts()
    # Other widgets
    discussion = FW.Forum()
    thread = FW.Thread()
    post = FW.Post()
    thread_header = FW.ThreadHeader()
    announcements_table = FW.AnnouncementsTable()
    discussion_header = FW.ForumHeader()


class ForumController(DiscussionController):
    M = ModelConfig
    W = WidgetConfig

    def _check_security(self):
        require_access(self.discussion, 'read')

    def __init__(self, forum_id):
        self.ThreadController = ForumThreadController
        self.PostController = ForumPostController
        self.moderate = ForumModerationController(self)
        self.discussion = DM.Forum.query.get(
            app_config_id=c.app.config._id,
            shortname=forum_id)
        if not self.discussion:
            raise exc.HTTPNotFound()
        super(ForumController, self).__init__()

    @expose()
    def _lookup(self, id=None, *remainder):
        if id and self.discussion:
            return ForumController(self.discussion.shortname + '/' + id), remainder
        else:
            raise exc.HTTPNotFound()

    @expose('jinja:forgediscussion:templates/index.html')
    @validate(dict(page=validators.Int(if_empty=0, if_invalid=0),
                   limit=validators.Int(if_empty=None, if_invalid=None)))
    def index(self, threads=None, limit=None, page=0, count=0, **kw):
        if self.discussion.deleted:
            redirect(self.discussion.url() + 'deleted')
        limit, page, start = g.handle_paging(limit, page)
        c.subscribed = M.Mailbox.subscribed(artifact=self.discussion)
        threads = DM.ForumThread.query.find(dict(discussion_id=self.discussion._id, num_replies={'$gt': 0})) \
                                      .sort([('flags', pymongo.DESCENDING), ('last_post_date', pymongo.DESCENDING)])
        c.discussion = self.W.discussion
        c.discussion_header = self.W.discussion_header
        c.whole_forum_subscription_form = self.W.subscribe_form
        return dict(
            discussion=self.discussion,
            count=threads.count(),
            threads=threads.skip(start).limit(int(limit)).all(),
            limit=limit,
            page=page)


    @expose('jinja:forgediscussion:templates/discussionforums/deleted.html')
    def deleted(self):
        return dict()

    @expose('json:')
    @require_post()
    @validate(W.subscribe_form)
    def subscribe_to_forum(self, subscribe=None, unsubscribe=None, shortname=None, **kw):
        if subscribe:
            self.discussion.subscribe(type='direct')
        elif unsubscribe:
            self.discussion.unsubscribe()
        return {
            'status': 'ok',
            'subscribed': M.Mailbox.subscribed(artifact=self.discussion),
            'subscribed_to_tool': M.Mailbox.subscribed(),
        }


class ForumThreadController(ThreadController):

    @expose('jinja:forgediscussion:templates/discussionforums/thread.html')
    @validate(dict(page=validators.Int(if_empty=0, if_invalid=0),
                   limit=validators.Int(if_empty=25, if_invalid=25)))
    def index(self, limit=25, page=0, count=0, **kw):
        if self.thread.discussion.deleted and not has_access(c.app, 'configure')():
            redirect(self.thread.discussion.url() + 'deleted')
        return super(ForumThreadController, self).index(limit=limit, page=page, count=count, show_moderate=True, **kw)

    @h.vardec
    @expose()
    @require_post()
    @validate(pass_validator, index)
    def moderate(self, **kw):
        require_access(self.thread, 'moderate')
        if self.thread.discussion.deleted and not has_access(c.app, 'configure')():
            redirect(self.thread.discussion.url() + 'deleted')
        args = self.W.moderate_thread.validate(kw, None)
        tasks.calc_forum_stats.post(self.thread.discussion.shortname)
        if args.pop('delete', None):
            url = self.thread.discussion.url()
            self.thread.delete()
            redirect(url)
        forum = args.pop('discussion')
        if forum != self.thread.discussion:
            tasks.calc_forum_stats.post(forum.shortname)
            self.thread.set_forum(forum)
        self.thread.flags = args.pop('flags', [])
        redirect(self.thread.url())


class ForumPostController(PostController):

    @h.vardec
    @expose('jinja:allura:templates/discussion/post.html')
    @validate(pass_validator)
    @utils.AntiSpam.validate('Spambot protection engaged')
    def index(self, **kw):
        if self.thread.discussion.deleted and not has_access(c.app, 'configure')():
            redirect(self.thread.discussion.url() + 'deleted')
        return super(ForumPostController, self).index(**kw)

    @expose()
    @require_post()
    @validate(pass_validator, error_handler=index)
    def moderate(self, **kw):
        require_access(self.post.thread, 'moderate')
        if self.thread.discussion.deleted and not has_access(c.app, 'configure')():
            redirect(self.thread.discussion.url() + 'deleted')
        tasks.calc_thread_stats.post(self.post.thread._id)
        tasks.calc_forum_stats(self.post.discussion.shortname)
        super(ForumPostController, self).moderate(**kw)


class ForumModerationController(ModerationController):
    PostModel = DM.ForumPost
