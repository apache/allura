import json
import logging
import pymongo
from urllib import urlencode, unquote

import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from tg import expose, validate, redirect, flash, response
from tg.decorators import with_trailing_slash
from pylons import g, c, request
from formencode import validators
from webob import exc

from ming.orm.base import session

from allura.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from allura.lib.security import require_access, has_access, require_authenticated
from allura.model import ProjectRole, Feed
from allura.lib.search import search
from allura.lib import helpers as h
from allura.lib.utils import AntiSpam
from allura.lib.decorators import require_post
from allura.controllers import BaseController

from .forum import ForumController
from forgediscussion import import_support
from forgediscussion import model
from forgediscussion import utils
from forgediscussion import widgets as FW
from allura.lib.widgets import discuss as DW
from allura.lib.widgets.search import SearchResults

from forgediscussion.widgets.admin import AddForumShort

log = logging.getLogger(__name__)

class RootController(BaseController):

    class W(object):
        forum_subscription_form=FW.ForumSubscriptionForm()
        new_topic=DW.NewTopicPost(submit_text='Save')
        announcements_table=FW.AnnouncementsTable()
        add_forum=AddForumShort()
        search_results = SearchResults()

    def _check_security(self):
        require_access(c.app, 'read')

    @with_trailing_slash
    @expose('jinja:forgediscussion:templates/discussionforums/index.html')
    def index(self, new_forum=False, **kw):
        c.new_topic = self.W.new_topic
        c.new_topic = self.W.new_topic
        c.add_forum = self.W.add_forum
        c.announcements_table = self.W.announcements_table
        announcements=model.ForumThread.query.find(dict(
                app_config_id=c.app.config._id,
                flags='Announcement',
                )).all()
        forums = model.Forum.query.find(dict(
                        app_config_id=c.app.config._id,
                        parent_id=None, deleted=False)).all()
        forums = [f for f in forums if h.has_access(f, 'read')()]
        threads = dict()
        for forum in forums:
            threads[forum._id] = model.ForumThread.query.find(dict(
                discussion_id=forum._id, num_replies={'$gt': 0})).sort('mod_date', pymongo.DESCENDING).limit(6).all()
        return dict(forums=forums,
                    threads=threads,
                    announcements=announcements,
                    hide_forum=(not new_forum))

    @expose('jinja:forgediscussion:templates/discussionforums/index.html')
    def new_forum(self, **kw):
        require_access(c.app, 'configure')
        return self.index(new_forum=True, **kw)

    @h.vardec
    @expose()
    @require_post()
    @validate(form=W.add_forum, error_handler=index)
    def add_forum_short(self, add_forum=None, **kw):
        require_access(c.app, 'configure')
        f = utils.create_forum(c.app, add_forum)
        redirect(f.url())

    @with_trailing_slash
    @expose('jinja:forgediscussion:templates/discussionforums/create_topic.html')
    def create_topic(self, new_forum=False, **kw):
        c.new_topic = self.W.new_topic
        forums = [f for f in model.Forum.query.find(dict(
                             app_config_id=c.app.config._id,
                             parent_id=None)).all() if has_access(f, 'post')() and not f.deleted]
        return dict(forums=forums)

    @h.vardec
    @expose()
    @require_post()
    @validate(W.new_topic, error_handler=create_topic)
    @AntiSpam.validate('Spambot protection engaged')
    def save_new_topic(self, subject=None, text=None, forum=None, **kw):
        discussion = model.Forum.query.get(
            app_config_id=c.app.config._id,
            shortname=forum)
        if discussion.deleted and not has_access(c.app, 'configure')():
            flash('This forum has been removed.')
            redirect(request.referrer)
        require_access(discussion, 'post')
        thd = discussion.get_discussion_thread(dict(
                headers=dict(Subject=subject)))
        post = thd.post(subject, text)
        flash('Message posted')
        redirect(thd.url())

    @with_trailing_slash
    @expose('jinja:forgediscussion:templates/discussionforums/search.html')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False),
                   project=validators.StringBool(if_empty=False),
                   limit=validators.Int(if_empty=None),
                   page=validators.Int(if_empty=0)))
    def search(self, q=None, history=False, project=False, limit=None, page=0, **kw):
        'local tool search'
        if project:
            redirect(c.project.url() + 'search?' + urlencode(dict(q=q, history=history)))
        results = []
        count=0
        limit, page, start = g.handle_paging(limit, page, default=25)
        if not q:
            q = ''
        else:
            results = search(
                q, rows=limit, start=start,
                fq=[
                    'is_history_b:%s' % history,
                    'project_id_s:%s' % c.project._id,
                    'mount_point_s:%s'% c.app.config.options.mount_point,
                    'deleted:false'])
            if results: count=results.hits
        c.search_results = self.W.search_results
        return dict(q=q, history=history, results=results or [],
                    count=count, limit=limit, page=page)

    @expose('jinja:allura:templates/markdown_syntax.html')
    def markdown_syntax(self):
        'Static page explaining markdown.'
        return dict()

    @expose()
    def _lookup(self, id=None, *remainder):
        if id:
            id = unquote(id)
            return ForumController(id), remainder
        else:
            raise exc.HTTPNotFound()

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

        feed = Feed.feed(
            dict(project_id=c.project._id, app_config_id=c.app.config._id),
            feed_type,
            title,
            c.app.url,
            title,
            since, until, page, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

class RootRestController(BaseController):

    @expose('json:')
    def validate_import(self, doc=None, username_mapping=None, **kw):
        require_access(c.project, 'admin')
        if username_mapping is None: username_mapping = {}
        try:
            doc = json.loads(doc)
            warnings, doc = import_support.validate_import(doc, username_mapping)
            return dict(warnings=warnings, errors=[])
        except Exception, e:
            raise
            log.exception(e)
            return dict(status=False, errors=[repr(e)])

    @expose('json:')
    def perform_import(
        self, doc=None, username_mapping=None, default_username=None, create_users=False,
        **kw):
        require_access(c.project, 'admin')
        if username_mapping is None: username_mapping = '{}'
        if c.api_token.get_capability('import') != [c.project.neighborhood.name, c.project.shortname]:
            log.error('Import capability is not enabled for %s', c.project.shortname)
            raise exc.HTTPForbidden(detail='Import is not allowed')
        try:
            doc = json.loads(doc)
            username_mapping = json.loads(username_mapping)
            warnings = import_support.perform_import(
                doc, username_mapping, default_username, create_users)
            return dict(warnings=warnings, errors=[])
        except Exception, e:
            raise
            log.exception(e)
            return dict(status=False, errors=[str(e)])
