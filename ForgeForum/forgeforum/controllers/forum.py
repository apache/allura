import shlex
import logging
from mimetypes import guess_type
from urllib import unquote

from tg import expose, validate, redirect, flash
from tg import request, response
from pylons import g, c
from ming.base import Object
from webob import exc

from pyforge.lib import helpers as h
from pyforge.lib.security import require, has_artifact_access
from pyforge.controllers import DiscussionController, ThreadController, PostController
from pyforge.lib.widgets import discuss as DW

from forgeforum import model
from forgeforum import widgets as FW

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
        return ForumController(self.discussion.shortname + '/' + id), remainder

    @h.vardec
    @expose()
    @validate(W.edit_post)
    def post(self, subject=None, text=None, **kw):
        require(has_artifact_access('post', self.discussion))
        thd = self.discussion.discussion_thread(dict(
                headers=dict(Subject=subject)))
        post = thd.post(subject, text)
        flash('Message posted')
        redirect(thd.url())

class ForumThreadController(ThreadController):

    @expose('pyforge.templates.discussion.thread')
    def index(self, **kw):
        return super(ForumThreadController, self).index(**kw)

    @h.vardec
    @expose()
    @validate(pass_validator, index)
    def moderate(self, **kw):
        require(has_artifact_access('moderate', self.thread))
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

    @expose()
    @validate(pass_validator, error_handler=PostController.index)
    def moderate(self, **kw):
        require(has_artifact_access('moderate', self.post.thread))
        args = self.W.moderate_post.validate(kw, None)
        g.publish('audit', 'Forum.thread_stats.%s' % self.post.thread._id)
        g.publish('audit', 'Forum.forum_stats.%s' % self.post.discussion.shortname.replace('/', '.'))
        if args.pop('promote', None):
            self.post.subject = args['subject']
            new_thread = self.post.promote()
            g.publish('audit', 'Forum.thread_stats.%s' % new_thread._id)
            redirect(request.referer)
        super(ForumPostController, self).moderate(**kw)

