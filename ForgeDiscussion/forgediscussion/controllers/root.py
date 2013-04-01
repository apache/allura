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
from urllib import unquote
from itertools import imap

from tg import expose, validate, redirect, flash, response
from tg.decorators import with_trailing_slash
from pylons import tmpl_context as c, app_globals as g
from pylons import request
from formencode import validators
from webob import exc

from allura.lib.security import require_access, has_access, require_authenticated
from allura.lib.search import search_app
from allura.lib import helpers as h
from allura.lib.utils import AntiSpam
from allura.lib.decorators import require_post
from allura.controllers import BaseController, DispatchIndex
from allura.controllers.feed import FeedArgs, FeedController

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

    class W(object):
        forum_subscription_form=FW.ForumSubscriptionForm()
        new_topic=DW.NewTopicPost(submit_text='Post')
        announcements_table=FW.AnnouncementsTable()
        add_forum=AddForumShort()
        search_results = SearchResults()
        search_help = SearchHelp(comments=False, history=False)

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
        return dict(forums=forums,
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
        return dict(forums=my_forums, current_forum=current_forum)

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
                headers=dict(Subject=subject)))[0]
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

    @expose('jinja:allura:templates/markdown_syntax.html')
    def markdown_syntax(self):
        'Static page explaining markdown.'
        return dict()

    @with_trailing_slash
    @expose('jinja:allura:templates/markdown_syntax_dialog.html')
    def markdown_syntax_dialog(self):
        'Static dialog page about how to use markdown.'
        return dict()

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

    def get_feed(self, project, app, user):
        """Return a :class:`allura.controllers.feed.FeedArgs` object describing
        the xml feed for this controller.

        Overrides :meth:`allura.controllers.feed.FeedController.get_feed`.

        """
        return FeedArgs(
            dict(project_id=project._id, app_config_id=app.config._id),
             'Recent posts to %s' % app.config.options.mount_label,
            app.url)


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
