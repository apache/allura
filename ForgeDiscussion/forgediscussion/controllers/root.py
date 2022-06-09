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

import json
import logging

import six
from six.moves.urllib.parse import unquote
from datetime import date, datetime, timedelta, time
import calendar
from collections import OrderedDict


from tg import expose, validate, redirect, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from tg import tmpl_context as c, app_globals as g
from tg import request
from formencode import validators
from webob import exc
import pymongo

from allura.lib.security import require_access, has_access, require_authenticated
from allura.lib.search import search_app
from allura.lib import helpers as h
from allura.lib import validators as v
from allura.lib.utils import AntiSpam, permanent_redirect
from allura.lib.decorators import require_post, memorable_forget
from allura.controllers import BaseController, DispatchIndex
from allura.controllers.rest import AppRestControllerMixin
from allura.controllers.feed import FeedArgs, FeedController
from allura import model as M

from .forum import ForumController
from forgediscussion import import_support
from forgediscussion import model
from forgediscussion import utils
from forgediscussion import widgets as FW
from allura.lib.widgets import discuss as DW
from allura.lib.widgets.search import SearchResults, SearchHelp

from forgediscussion.widgets.admin import AddForumShort

log = logging.getLogger(__name__)


class RootController(BaseController, DispatchIndex, FeedController):

    class W:
        new_topic = DW.NewTopicPost(submit_text='Post')

        announcements_table = FW.AnnouncementsTable()
        add_forum = AddForumShort()
        search_results = SearchResults()
        search_help = SearchHelp(comments=False, history=False,
                                 fields={'author_user_name_t': 'Username',
                                         'text': '"Post text"',
                                         'timestamp_dt': 'Date posted.  Example: timestamp_dt:[2018-01-01T00:00:00Z TO *]',
                                         'name_s': 'Subject'})

    def _check_security(self):
        require_access(c.app, 'read')

    @with_trailing_slash
    @expose('jinja:forgediscussion:templates/discussionforums/index.html')
    def index(self, new_forum=False, **kw):
        c.add_forum = self.W.add_forum
        c.announcements_table = self.W.announcements_table
        announcements = model.ForumThread.query.find(dict(
            app_config_id=c.app.config._id,
            flags='Announcement',
        )).all()
        forums = model.Forum.query.find(dict(
            app_config_id=c.app.config._id,
            parent_id=None, deleted=False)).all()
        forums = [f for f in forums if h.has_access(f, 'read')()]
        noindex = all([f.num_topics == 0 for f in forums])
        return dict(forums=forums,
                    announcements=announcements,
                    hide_forum=(not new_forum),
                    noindex=noindex)

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
    def create_topic(self, forum_name=None, new_forum=False, **kw):
        forums = model.Forum.query.find(dict(app_config_id=c.app.config._id,
                                             parent_id=None,
                                             deleted=False))
        c.new_topic = self.W.new_topic
        my_forums = []
        forum_name = h.really_unicode(unquote(forum_name)) if forum_name else None
        current_forum = None
        for f in forums:
            if forum_name == f.shortname:
                current_forum = f
            if has_access(f, 'post')():
                my_forums.append(f)
        return dict(forums=my_forums,
                    current_forum=current_forum,
                    subscribed=M.Mailbox.subscribed(artifact=current_forum),
                    subscribed_to_tool=M.Mailbox.subscribed(),
                    )

    @memorable_forget()
    @h.vardec
    @expose()
    @require_post()
    @validate(W.new_topic, error_handler=create_topic)
    @AntiSpam.validate('Spambot protection engaged', error_url='create_topic')
    def save_new_topic(self, subject=None, text=None, forum=None, subscribe=False, **kw):
        self.rate_limit(model.ForumPost, 'Topic creation', six.ensure_text(request.referer or '/'))
        discussion = model.Forum.query.get(
            app_config_id=c.app.config._id,
            shortname=forum)
        if discussion.deleted and not has_access(c.app, 'configure')():
            flash('This forum has been removed.')
            redirect(six.ensure_text(request.referer or '/'))
        require_access(discussion, 'post')
        thd = discussion.get_discussion_thread(dict(
            headers=dict(Subject=subject)))[0]
        p = thd.post(subject, text, subscribe=subscribe)
        if 'attachment' in kw:
            p.add_multiple_attachments(kw['attachment'])
        thd.post_to_feed(p)
        flash('Message posted')
        redirect(thd.url())

    @with_trailing_slash
    @expose('jinja:forgediscussion:templates/discussionforums/search.html')
    @validate(dict(q=v.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False),
                   project=validators.StringBool(if_empty=False),
                   limit=validators.Int(if_empty=None, if_invalid=None),
                   page=validators.Int(if_empty=0, if_invalid=0)))
    def search(self, q=None, history=None, project=None, limit=None, page=0, **kw):
        c.search_results = self.W.search_results
        c.help_modal = self.W.search_help
        search_params = kw
        search_params.update({
            'q': q or '',
            'history': history,
            'project': project,
            'limit': limit,
            'page': page,
            'allowed_types': ['Post', 'Post Snapshot', 'Discussion', 'Thread'],
        })
        d = search_app(**search_params)
        d['search_comments_disable'] = True
        return d

    @expose()
    def markdown_syntax(self, **kw):
        permanent_redirect('/nf/markdown_syntax')

    @expose()
    def _lookup(self, id=None, *remainder):
        if id:
            id = unquote(id)
            forum = model.Forum.query.get(
                app_config_id=c.app.config._id,
                shortname=id)
            if forum is None:
                raise exc.HTTPNotFound()
            c.forum = forum
            return ForumController(id), remainder
        else:
            raise exc.HTTPNotFound()

    def get_feed(self, project, app, user):
        """Return a :class:`allura.controllers.feed.FeedArgs` object describing
        the xml feed for this controller.

        Overrides :meth:`allura.controllers.feed.FeedController.get_feed`.

        """
        return FeedArgs(
            dict(project_id=project._id, app_config_id=app.config._id),
            'Recent posts to %s' % app.config.options.mount_label,
            app.url)

    @without_trailing_slash
    @expose('jinja:forgediscussion:templates/discussionforums/stats_graph.html')
    def stats(self, dates=None, forum=None, **kw):
        if not dates:
            dates = "{} to {}".format(
                (date.today() - timedelta(days=60)).strftime('%Y-%m-%d'),
                date.today().strftime('%Y-%m-%d'))
        return dict(
            dates=dates,
            selected_forum=forum,
        )

    @expose('json:')
    @validate(dict(
        begin=h.DateTimeConverter(not_empty=True),
        end=h.DateTimeConverter(not_empty=True),
    ), error_handler=exc.HTTPBadRequest)
    def stats_data(self, begin=None, end=None, forum=None, **kw):
        end = end or date.today()
        begin = begin or end - timedelta(days=60)

        discussion_id_q = {
            '$in': [d._id for d in c.app.forums
                    if d.shortname == forum or not forum]
        }
        # must be ordered dict, so that sorting by this works properly
        grouping = OrderedDict()
        grouping['year'] = {'$year': '$timestamp'}
        grouping['month'] = {'$month': '$timestamp'}
        grouping['day'] = {'$dayOfMonth': '$timestamp'}
        mongo_data = model.ForumPost.query.aggregate([
            {'$match': {
                'discussion_id': discussion_id_q,
                'status': 'ok',
                'timestamp': {
                    # convert date to datetime to make pymongo happy
                    '$gte': datetime.combine(begin, time.min),
                    '$lte': datetime.combine(end, time.max),
                },
                'deleted': False,
            }},
            {'$group': {
                '_id': grouping,
                'posts': {'$sum': 1},
            }},
            {'$sort': {
                '_id': pymongo.ASCENDING,
            }},
        ], cursor={})

        def reformat_data(mongo_data):
            def item(day, val):
                return [
                    calendar.timegm(day.timetuple()) * 1000,
                    val
                ]

            next_expected_date = begin
            for d in mongo_data:
                this_date = datetime(
                    d['_id']['year'], d['_id']['month'], d['_id']['day'])
                for day in h.daterange(next_expected_date, this_date):
                    yield item(day, 0)
                yield item(this_date, d['posts'])
                next_expected_date = this_date + timedelta(days=1)
            for day in h.daterange(next_expected_date, end + timedelta(days=1)):
                yield item(day, 0)

        return dict(
            begin=begin,
            end=end,
            data=list(reformat_data(mongo_data)),
        )


class RootRestController(BaseController, AppRestControllerMixin):

    def _check_security(self):
        require_access(c.app, 'read')

    @expose()
    def _lookup(self, forum, *remainder):
        return ForumRestController(unquote(forum)), remainder

    @expose('json:')
    def index(self, limit=None, page=0, **kw):
        limit, page, start = g.handle_paging(limit, int(page))
        forums = model.Forum.query.find(dict(
            app_config_id=c.app.config._id,
            parent_id=None, deleted=False)
        ).sort([('shortname', pymongo.ASCENDING)]).skip(start).limit(limit)
        count = forums.count()
        json = dict(forums=[dict(_id=f._id,
                                 name=f.name,
                                 shortname=f.shortname,
                                 description=f.description,
                                 num_topics=f.num_topics,
                                 last_post=f.last_post,
                                 url=h.absurl('/rest' + f.url()))
                            for f in forums if has_access(f, 'read')])
        json['limit'] = limit
        json['page'] = page
        json['count'] = count
        return json

    @expose('json:')
    def validate_import(self, doc=None, username_mapping=None, **kw):
        require_access(c.project, 'admin')
        if username_mapping is None:
            username_mapping = {}
        try:
            doc = json.loads(doc)
            warnings, doc = import_support.validate_import(
                doc, username_mapping)
            return dict(warnings=warnings, errors=[])
        except Exception as e:
            raise
            log.exception(e)
            return dict(status=False, errors=[repr(e)])

    @expose('json:')
    def perform_import(
            self, doc=None, username_mapping=None, default_username=None, create_users=False,
            **kw):
        require_access(c.project, 'admin')
        if username_mapping is None:
            username_mapping = '{}'
        if not c.api_token.can_import_forum():
            log.error('Import capability is not enabled for %s', c.project.shortname)
            raise exc.HTTPForbidden(detail='Import is not allowed')
        try:
            doc = json.loads(doc)
            username_mapping = json.loads(username_mapping)
            warnings = import_support.perform_import(
                doc, username_mapping, default_username, create_users)
            return dict(warnings=warnings, errors=[])
        except Exception as e:
            raise
            log.exception(e)
            return dict(status=False, errors=[str(e)])


class ForumRestController(BaseController):

    def __init__(self, forum):
        self.forum = model.Forum.query.get(
            app_config_id=c.app.config._id,
            shortname=forum)
        if not self.forum or self.forum.deleted:
            raise exc.HTTPNotFound()

    def _check_security(self):
        require_access(self.forum, 'read')

    @expose('json:')
    def index(self, limit=None, page=0, **kw):
        limit, page, start = g.handle_paging(limit, int(page))
        topics = model.Forum.thread_class().query.find(dict(discussion_id=self.forum._id))
        topics = topics.sort([('flags', pymongo.DESCENDING),
                              ('last_post_date', pymongo.DESCENDING)])
        topics = topics.skip(start).limit(limit)
        count = topics.count()
        json = {}
        json['forum'] = self.forum.__json__(limit=1)  # small limit since we're going to "del" the threads anyway
        # topics replace threads here
        del json['forum']['threads']
        json['forum']['topics'] = [dict(_id=t._id,
                                        subject=t.subject,
                                        num_replies=t.num_replies,
                                        num_views=t.num_views,
                                        url=h.absurl('/rest' + t.url()),
                                        last_post=t.last_post)
                                   for t in topics if t.status == 'ok']
        json['count'] = count
        json['page'] = page
        json['limit'] = limit
        return json

    @expose()
    def _lookup(self, thread, thread_id, *remainder):
        if thread == 'thread':
            topic = model.Forum.thread_class().query.find(dict(
                app_config_id=c.app.config._id,
                discussion_id=self.forum._id,
                _id=unquote(thread_id))).first()
            if topic:
                return ForumTopicRestController(self.forum, topic), remainder
        raise exc.HTTPNotFound()


class ForumTopicRestController(BaseController):

    def __init__(self, forum, topic):
        self.forum = forum
        self.topic = topic

    def _check_security(self):
        require_access(self.forum, 'read')

    @expose('json:')
    def index(self, limit=None, page=0, **kw):
        limit, page, start = g.handle_paging(limit, int(page))
        json_data = {}
        json_data['topic'] = self.topic.__json__(limit=limit, page=page)
        json_data['count'] = self.topic.query_posts(status='ok').count()
        json_data['page'] = page
        json_data['limit'] = limit
        return json_data
