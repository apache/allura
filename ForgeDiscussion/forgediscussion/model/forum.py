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

import re
import logging
from itertools import chain
import typing

import pymongo
from tg import tmpl_context as c
from ming import schema
from ming.utils import LazyProperty
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty, Mapper

from tg import config as tg_config

from allura import model as M
from allura.model.notification import MailFooter
from allura.lib import utils
from allura.lib import helpers as h
from allura.lib.decorators import memoize

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


config = utils.ConfigProxy(
    common_suffix='forgemail.domain')

log = logging.getLogger(__name__)


class Forum(M.Discussion):

    class __mongometa__:
        name = 'forum'

    query: 'Query[Forum]'

    type_s = 'Discussion'

    parent_id = FieldProperty(schema.ObjectId, if_missing=None)
    threads = RelationProperty('ForumThread', via='discussion_id')
    posts = RelationProperty('ForumPost', via='discussion_id')
    members_only = FieldProperty(bool, if_missing=False)
    anon_posts = FieldProperty(bool, if_missing=False)
    monitoring_email = FieldProperty(str, if_missing=None)

    @classmethod
    def attachment_class(cls):
        return ForumAttachment

    @classmethod
    def thread_class(cls):
        return ForumThread

    @property
    def parent(self):
        return Forum.query.get(_id=self.parent_id)

    @property
    def subforums(self):
        return Forum.query.find(dict(parent_id=self._id)).all()

    @property
    def email_address(self):
        if c.app.config.options.get('AllowEmailPosting', True):
            domain = self.email_domain
            local_part = self.shortname.replace('/', '.')
            return f'{local_part}@{domain}{config.common_suffix}'
        else:
            return tg_config.get('forgemail.return_path')

    @LazyProperty
    def announcements(self):
        return self.thread_class().query.find(dict(
            app_config_id=self.app_config_id,
            flags='Announcement')).all()

    def breadcrumbs(self):
        if self.parent:
            l = self.parent.breadcrumbs()
        else:
            l = []
        return l + [(self.name, self.url())]

    def url(self):
        return h.urlquote(self.app.url + self.shortname + '/')

    def delete(self):
        # Delete the subforums
        for sf in self.subforums:
            sf.delete()
        super().delete()

    def get_discussion_thread(self, data=None):
        # If the data is a reply, use the parent's thread
        subject = '[no subject]'
        if data is not None:
            message_id = data.get('message_id') or ''
            subject = data['headers'].get('Subject', subject)
            in_reply_to = data.get('in_reply_to') or []
            references = data.get('references') or []
            # find first valid In-Reply-To: header or References: header (starting from end)
            for msg_id in in_reply_to + list(reversed(references)):
                parent_id = msg_id.split('/')[-1]
                parent = self.post_class().query.get(_id=parent_id)
                if parent:
                    return parent.thread, parent_id
        if message_id:
            post = self.post_class().query.get(_id=message_id)
            if post:
                return post.thread, None
        # Otherwise it's a new thread
        return self.thread_class()(discussion_id=self._id, subject=subject), None

    @property
    def discussion_thread(self):
        return None

    def get_mail_footer(self, notification, toaddr):
        if toaddr and toaddr == self.monitoring_email:
            return MailFooter.monitored(
                toaddr,
                h.absurl(self.url()),
                h.absurl('{}admin/{}/forums'.format(
                    self.project.url(),
                    self.app.config.options.mount_point)))
        return super().get_mail_footer(notification, toaddr)


class ForumThread(M.Thread):

    class __mongometa__:
        name = 'forum_thread'
        indexes = [
            'flags',
            'discussion_id',
            'import_id',  # may be used by external legacy systems
        ]

    query: 'Query[ForumThread]'

    type_s = 'Thread'

    discussion_id = ForeignIdProperty(Forum)
    first_post_id = ForeignIdProperty('ForumPost')
    flags = FieldProperty([str])

    discussion = RelationProperty(Forum)
    posts = RelationProperty('ForumPost', via='thread_id')
    first_post = RelationProperty('ForumPost', via='first_post_id')

    @property
    def type_name(self):
        return 'topic'

    @property
    def status(self):
        if len(self.posts) == 1:
            return self.posts[0].status
        else:
            return 'ok'

    @classmethod
    def attachment_class(cls):
        return ForumAttachment

    @property
    def email_address(self):
        return self.discussion.email_address

    def primary(self):
        return self

    @memoize
    def subscribed(self, user=None, include_parents=True):
        subbed = super().subscribed(user=user, include_parents=include_parents)
        if subbed:
            return subbed
        if include_parents:
            if user is None:
                user = c.user
            forum = self.discussion
            forum_subscribed = M.Mailbox.subscribed(artifact=forum, user_id=user._id)
            if forum_subscribed:
                return True
        return False

    def post(self, subject, text, message_id=None, parent_id=None, **kw):
        post = super().post(text, message_id=message_id, parent_id=parent_id, **kw)
        if not self.first_post_id:
            self.first_post_id = post._id
            self.num_replies = 1
        return post

    def set_forum(self, new_forum):
        self.post_class().query.update(
            dict(discussion_id=self.discussion_id, thread_id=self._id),
            {'$set': dict(discussion_id=new_forum._id)}, multi=True)
        self.attachment_class().query.update(
            {'discussion_id': self.discussion_id, 'thread_id': self._id},
            {'$set': dict(discussion_id=new_forum._id)}, multi=True)
        self.discussion_id = new_forum._id


class ForumPostHistory(M.PostHistory):

    class __mongometa__:
        name = 'post_history'

    query: 'Query[ForumPostHistory]'

    artifact_id = ForeignIdProperty('ForumPost')


class ForumPost(M.Post):

    class __mongometa__:
        name = 'forum_post'
        history_class = ForumPostHistory
        indexes = [
            'timestamp',  # for the posts_24hr site_stats query
            (  # for last_post queries on thread listing page
                'thread_id',
                'deleted',
                ('timestamp', pymongo.DESCENDING),
            ),
        ]

    query: 'Query[ForumPost]'

    type_s = 'Post'

    discussion_id = ForeignIdProperty(Forum)
    thread_id = ForeignIdProperty(ForumThread)

    discussion = RelationProperty(Forum)
    thread = RelationProperty(ForumThread)

    @classmethod
    def attachment_class(cls):
        return ForumAttachment

    @property
    def email_address(self):
        return self.discussion.email_address

    def primary(self):
        return self


class ForumAttachment(M.DiscussionAttachment):
    DiscussionClass = Forum
    ThreadClass = ForumThread
    PostClass = ForumPost

    class __mongometa__:
        polymorphic_identity = 'ForumAttachment'

    query: 'Query[ForumAttachment]'

    attachment_type = FieldProperty(str, if_missing='ForumAttachment')


Mapper.compile_all()
