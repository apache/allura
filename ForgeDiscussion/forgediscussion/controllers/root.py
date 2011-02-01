import logging
import pymongo
from urllib import urlencode, unquote

from tg import expose, validate, redirect, flash, response
from tg.decorators import with_trailing_slash
from pylons import g, c, request
from formencode import validators
from webob import exc

from ming.orm.base import session

from allura.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from allura.lib.security import require, has_artifact_access, has_project_access, require_authenticated
from allura.model import ProjectRole, Feed
from allura.lib.search import search
from allura.lib import helpers as h
from allura.controllers import BaseController

from .forum import ForumController
from forgediscussion import model
from forgediscussion import widgets as FW
from allura.lib.widgets import discuss as DW

log = logging.getLogger(__name__)

class RootController(BaseController):

    class W(object):
        forum_subscription_form=FW.ForumSubscriptionForm()
        new_topic=DW.NewTopicPost(submit_text='Save')
        announcements_table=FW.AnnouncementsTable()

    def _check_security(self):
        require(has_artifact_access('read'))

    @with_trailing_slash
    @expose('jinja:discussionforums/index.html')
    def index(self, new_forum=False, **kw):
        c.new_topic = self.W.new_topic
        c.announcements_table = self.W.announcements_table
        announcements=model.ForumThread.query.find(dict(
                flags='Announcement')).all()
        forums = model.Forum.query.find(dict(
                        app_config_id=c.app.config._id,
                        parent_id=None)).all()
        threads = dict()
        for forum in forums:
            threads[forum._id] = model.ForumThread.query.find(dict(
                            discussion_id=forum._id)).sort('mod_date', pymongo.DESCENDING).limit(6).all()
        return dict(forums=forums,
                    threads=threads,
                    announcements=announcements,
                    hide_forum=(not new_forum))

    @with_trailing_slash
    @expose('jinja:discussionforums/create_topic.html')
    def create_topic(self, new_forum=False, **kw):
        c.new_topic = self.W.new_topic
        forums = model.Forum.query.find(dict(
                        app_config_id=c.app.config._id,
                        parent_id=None)).all()
        return dict(forums=forums)

    @h.vardec
    @expose()
    @validate(W.new_topic, error_handler=create_topic)
    def save_new_topic(self, subject=None, text=None, forum=None, **kw):
        discussion = model.Forum.query.get(
            app_config_id=c.app.config._id,
            shortname=forum)
        if discussion.deleted and not has_artifact_access('configure', app=c.app)():
            flash('This forum has been removed.')
            redirect(request.referrer)
        require(has_artifact_access('post', discussion))
        thd = discussion.get_discussion_thread(dict(
                headers=dict(Subject=subject)))
        post = thd.post(subject, text)
        flash('Message posted')
        redirect(thd.url())

    @with_trailing_slash
    @expose('jinja:discussionforums/search.html')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False),
                   project=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=False, project=False):
        'local tool search'
        if project:
            redirect(c.project.url() + 'search?' + urlencode(dict(q=q, history=history)))
        results = []
        count=0
        if not q:
            q = ''
        else:
            results = search(
                q,
                fq=[
                    'is_history_b:%s' % history,
                    'project_id_s:%s' % c.project._id,
                    'mount_point_s:%s'% c.app.config.options.mount_point ])
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

    @expose('jinja:markdown_syntax.html')
    def markdown_syntax(self):
        'Static page explaining markdown.'
        return dict()

    @expose('jinja:discussionforums/help.html')
    def help(self):
        'Static help page.'
        return dict()

    @expose()
    def _lookup(self, id=None, *remainder):
        if id:
            id = unquote(id)
            return ForumController(id), remainder
        else:
            raise exc.HTTPNotFound()

    # FIXME this code is not used, but it should be so we can do Forum-level subscriptions
    @h.vardec
    @expose()
    @validate(W.forum_subscription_form)
    def subscribe(self, **kw):
        require_authenticated()
        forum = kw.pop('forum', [])
        thread = kw.pop('thread', [])
        objs = []
        for data in forum:
            objs.append(dict(obj=model.Forum.query.get(shortname=data['shortname'],
                                                       app_config_id=c.app.config._id),
                             subscribed=bool(data.get('subscribed'))))
        for data in thread:
            objs.append(dict(obj=model.Thread.query.get(_id=data['id']),
                             subscribed=bool(data.get('subscribed'))))
        for obj in objs:
            if obj['subscribed']:
                obj['obj'].subscriptions[str(c.user._id)] = True
            else:
                obj['obj'].subscriptions.pop(str(c.user._id), None)
        redirect(request.referer)

    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None),
            until=h.DateTimeConverter(if_empty=None),
            page=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, page=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent posts to %s' % c.app.config.options.mount_label

        forums = model.Forum.query.find(dict(
                        app_config_id=c.app.config._id,
                        parent_id=None)).all()
        threads = []
        for forum in forums:
            threads += model.ForumThread.query.find(dict(
                            discussion_id=forum._id)).sort('mod_date', pymongo.DESCENDING).limit(6).all()

        feed = Feed.feed(
            {'artifact_reference':{'$in': [t.dump_ref() for t in threads]}},
            feed_type,
            title,
            c.app.url,
            title,
            since, until, page, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')
