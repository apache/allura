import logging
import pymongo

from tg import expose, validate, redirect
from tg import request, response
from pylons import g, c
from webob import exc

from allura.lib import helpers as h
from allura import model as M
from allura.lib.security import require, has_artifact_access
from allura.lib.decorators import require_post
from allura.controllers import DiscussionController, ThreadController, PostController, ModerationController
from allura.lib.widgets import discuss as DW

from forgediscussion import model as DM
from forgediscussion import widgets as FW

log = logging.getLogger(__name__)

class pass_validator(object):
    def validate(self, v, s):
        return v
pass_validator=pass_validator()

class ModelConfig(object):
    Discussion=DM.Forum
    Thread=DM.ForumThread
    Post=DM.ForumPost
    Attachment=M.DiscussionAttachment

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

    @expose('jinja:allura:templates/discussion/index.html')
    def index(self, threads=None, limit=None, page=0, count=0, **kw):
        if self.discussion.deleted and not has_artifact_access('configure', app=c.app)():
            redirect(self.discussion.url()+'deleted')
        limit, page, start = g.handle_paging(limit, page)
        threads = DM.ForumThread.query.find(dict(discussion_id=self.discussion._id)) \
                                      .sort([('flags', pymongo.DESCENDING), ('mod_date', pymongo.DESCENDING)])
        return super(ForumController, self).index(threads=threads.skip(start).limit(int(limit)).all(), limit=limit, page=page, count=threads.count(), **kw)

    @expose()
    def icon(self):
        return self.discussion.icon.serve()

    @expose('jinja:forgediscussion:templates/discussionforums/deleted.html')
    def deleted(self):
        return dict()


class ForumThreadController(ThreadController):

    @expose('jinja:forgediscussion:templates/discussionforums/thread.html')
    def index(self, limit=None, page=0, count=0, **kw):
        if self.thread.discussion.deleted and not has_artifact_access('configure', app=c.app)():
            redirect(self.thread.discussion.url()+'deleted')
        return super(ForumThreadController, self).index(limit=limit, page=page, count=count, show_moderate=True, **kw)

    @h.vardec
    @expose()
    @require_post()
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
        forum = args.pop('discussion')
        if forum != self.thread.discussion:
            g.publish('audit', 'Forum.forum_stats.%s' % forum.shortname.replace('/', '.'))
            self.thread.set_forum(forum)
        self.thread.flags = args.pop('flags', [])
        redirect(self.thread.url())

class ForumPostController(PostController):

    @expose('jinja:allura:templates/discussion/post.html')
    def index(self, **kw):
        if self.thread.discussion.deleted and not has_artifact_access('configure', app=c.app)():
            redirect(self.thread.discussion.url()+'deleted')
        return super(ForumPostController, self).index(**kw)

    @expose()
    @require_post()
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

class ForumModerationController(ModerationController):
    PostModel = DM.ForumPost
