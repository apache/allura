import shlex
import logging
import pymongo
from mimetypes import guess_type
from urllib import unquote

from tg import expose, validate, redirect, flash
from tg import request, response
import tg
from pylons import g, c
from ming.base import Object
from webob import exc

from allura.lib import helpers as h
from allura.lib.security import require, has_artifact_access
from allura.controllers import DiscussionController, ThreadController, PostController
from allura.lib.widgets import discuss as DW

from forgediscussion import model
from forgediscussion import widgets as FW

log = logging.getLogger(__name__)

class pass_validator(object):
    def validate(self, v, s):
        return v
pass_validator=pass_validator()

class ModelConfig(object):
    Discussion=model.Forum
    Thread=model.ForumThread
    Post=model.ForumPost
    Attachment=model.ForumAttachment

class WidgetConfig(object):
    # Forms
    subscription_form = DW.SubscriptionForm()
    edit_post = DW.EditPost(show_subject=True)
    moderate_post = FW.ModeratePost()
    moderate_thread = FW.ModerateThread()
    flag_post = DW.FlagPost()
    post_filter = DW.PostFilter()
    moderate_posts=DW.ModeratePosts()
    # Other widgets
    discussion = FW.Forum()
    thread = FW.Thread()
    post = FW.Post()
    thread_header = FW.ThreadHeader()
    announcements_table = FW.AnnouncementsTable()

class ForumController(DiscussionController):
    M=ModelConfig
    W=WidgetConfig

    def _check_security(self):
        require(has_artifact_access('read', self.discussion))

    def __init__(self, forum_id):
        self.ThreadController = ForumThreadController
        self.PostController = ForumPostController
        self.discussion = model.Forum.query.get(
            app_config_id=c.app.config._id,
            shortname=forum_id)
        super(ForumController, self).__init__()

    @expose()
    def _lookup(self, id, *remainder):
        if self.discussion:
            return ForumController(self.discussion.shortname + '/' + id), remainder
        else:
            raise exc.HTTPNotFound()

    @expose('allura.templates.discussion.index')
    def index(self, threads=None, limit=None, page=0, count=0, **kw):
        if self.discussion.deleted and not has_artifact_access('configure', app=c.app)():
            redirect(self.discussion.url()+'deleted')
        limit, page, start = g.handle_paging(limit, page)
        threads = model.ForumThread.query.find(dict(discussion_id=self.discussion._id)).sort('mod_date', pymongo.DESCENDING)
        return super(ForumController, self).index(threads=threads.skip(start).limit(int(limit)).all(), limit=limit, page=page, count=threads.count(), **kw)

    @h.vardec
    @expose()
    @validate(W.edit_post)
    def post(self, subject=None, text=None, **kw):
        if not subject:
            flash('You must have a subject for this post.')
            redirect(request.referrer)
        if self.discussion.deleted and not has_artifact_access('configure', app=c.app)():
            redirect(self.deleted)
        if 'new_topic' in kw:
            subject = kw['new_topic']['subject']
            text = kw['new_topic']['text']
        require(has_artifact_access('post', self.discussion))
        thd = self.discussion.discussion_thread(dict(
                headers=dict(Subject=subject)))
        post = thd.post(subject, text)
        thd.first_post_id = post._id
        flash('Message posted')
        redirect(thd.url())

    @expose()
    def icon(self):
        with self.discussion.icon.open() as fp:
            filename = fp.metadata['filename'].encode('utf-8')
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type.encode('utf-8')
            return fp.read()
        return self.discussion.icon.filename

    @expose('forgediscussion.templates.deleted')
    def deleted(self):
        return dict()


class ForumThreadController(ThreadController):

    @expose('allura.templates.discussion.thread')
    def index(self, limit=None, page=0, count=0, **kw):
        if self.thread.discussion.deleted and not has_artifact_access('configure', app=c.app)():
            redirect(self.thread.discussion.url()+'deleted')
        return super(ForumThreadController, self).index(limit=limit, page=page, count=count, **kw)

    @h.vardec
    @expose()
    @validate(pass_validator, index)
    def moderate(self, **kw):
        require(has_artifact_access('moderate', self.thread))
        if self.thread.discussion.deleted and not has_artifact_access('configure', app=c.app)():
            redirect(self.thread.discussion.url()+'deleted')
        args = self.W.moderate_thread.validate(kw, None)
        g.publish('audit', 'Forum.forum_stats.%s' % self.thread.discussion.shortname.replace('/', '.'))
        if args.pop('delete', None):
            url = self.thread.discussion.url()
            self.thread.delete()
            redirect(url)
        forum = args.pop('forum')
        if forum != self.thread.discussion:
            g.publish('audit', 'Forum.forum_stats.%s' % forum.shortname.replace('/', '.'))
            self.thread.set_forum(forum)
        self.thread.flags = args.pop('flags', [])
        redirect(self.thread.url())

class ForumPostController(PostController):

    @expose('allura.templates.discussion.post')
    def index(self, **kw):
        if self.thread.discussion.deleted and not has_artifact_access('configure', app=c.app)():
            redirect(self.thread.discussion.url()+'deleted')
        return super(ForumPostController, self).index(**kw)

    @expose()
    @validate(pass_validator, error_handler=index)
    def moderate(self, **kw):
        require(has_artifact_access('moderate', self.post.thread))
        if self.thread.discussion.deleted and not has_artifact_access('configure', app=c.app)():
            redirect(self.thread.discussion.url()+'deleted')
        args = self.W.moderate_post.validate(kw, None)
        g.publish('audit', 'Forum.thread_stats.%s' % self.post.thread._id)
        g.publish('audit', 'Forum.forum_stats.%s' % self.post.discussion.shortname.replace('/', '.'))
        if args.pop('promote', None):
            self.post.subject = args['subject']
            new_thread = self.post.promote()
            g.publish('audit', 'Forum.thread_stats.%s' % new_thread._id)
            redirect(request.referer)
        super(ForumPostController, self).moderate(**kw)

