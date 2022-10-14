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

import os
import logging
from datetime import datetime
import typing

import jinja2
import markupsafe
import pymongo
from pymongo.errors import DuplicateKeyError
from tg import tmpl_context as c, app_globals as g
import tg

from ming import schema
from ming.orm.base import session
from ming.orm.property import (FieldProperty, RelationProperty,
                               ForeignIdProperty)
from ming.utils import LazyProperty
from bson import ObjectId

from allura.lib import helpers as h
from allura.lib import security
from allura.lib.security import require_access, has_access
from allura.lib import utils
from allura.model.notification import Notification, Mailbox
from .artifact import Artifact, ArtifactReference, VersionedArtifact, Snapshot, Message, Feed, ReactableArtifact
from .attachments import BaseAttachment
from .auth import User, ProjectRole, AlluraUserProperty
from .timeline import ActivityObject
from .types import MarkdownCache

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query

log = logging.getLogger(__name__)


class Discussion(Artifact, ActivityObject):

    class __mongometa__:
        name = 'discussion'

    query: 'Query[Discussion]'

    type_s = 'Discussion'

    parent_id = FieldProperty(schema.Deprecated)
    shortname = FieldProperty(str)
    name = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    description_cache = FieldProperty(MarkdownCache)
    num_topics = FieldProperty(int, if_missing=0)
    num_posts = FieldProperty(int, if_missing=0)
    subscriptions = FieldProperty({str: bool})

    threads = RelationProperty('Thread', via='discussion_id')
    posts = RelationProperty('Post', via='discussion_id')

    def __json__(self, limit=None, posts_limit=None, is_export=False):
        return dict(
            _id=str(self._id),
            shortname=self.shortname,
            name=self.name,
            description=self.description,
            threads=[t.__json__(limit=posts_limit, is_export=is_export) for t
                     in self.thread_class().query.find(dict(discussion_id=self._id)).limit(limit or 0)]
        )

    @property
    def activity_name(self):
        return 'discussion %s' % self.name

    @classmethod
    def thread_class(cls):
        return cls.threads.related

    @classmethod
    def post_class(cls):
        return cls.posts.related

    @classmethod
    def attachment_class(cls):
        return DiscussionAttachment

    def update_stats(self):
        self.num_topics = self.thread_class().query.find(
            dict(discussion_id=self._id)).count()
        self.num_posts = self.post_class().query.find(
            dict(discussion_id=self._id, status='ok', deleted=False)).count()

    @LazyProperty
    def last_post(self):
        q = self.post_class().query.find(dict(
            discussion_id=self._id,
            status='ok',
            deleted=False,
        )).sort('timestamp', pymongo.DESCENDING).limit(1)
        return q.first()

    def url(self):
        return self.app.url + '_discuss/'

    def shorthand_id(self):
        return self.shortname

    def index(self):
        result = Artifact.index(self)
        result.update(
            title=self.name,
            name_s=self.name,
            text=self.description)
        return result

    def delete(self):
        # Delete all the threads, posts, and artifacts
        self.thread_class().query.remove(dict(discussion_id=self._id))
        self.post_class().query.remove(dict(discussion_id=self._id))
        self.attachment_class().remove(dict(discussion_id=self._id))
        super().delete()

    def find_posts(self, **kw):
        q = dict(kw, discussion_id=self._id, deleted=False)
        return self.post_class().query.find(q)


class Thread(Artifact, ActivityObject):

    class __mongometa__:
        name = 'thread'
        indexes = [
            ('artifact_id',),
            ('ref_id',),
            (('app_config_id', pymongo.ASCENDING),
             ('last_post_date', pymongo.DESCENDING),
             ('mod_date', pymongo.DESCENDING)),
            ('discussion_id',),
        ]

    query: 'Query[Thread]'

    type_s = 'Thread'

    _id = FieldProperty(str, if_missing=lambda: h.nonce(10))
    discussion_id = ForeignIdProperty(Discussion)
    ref_id: str = ForeignIdProperty('ArtifactReference')
    subject = FieldProperty(str, if_missing='')
    num_replies = FieldProperty(int, if_missing=0)
    num_views = FieldProperty(int, if_missing=0)
    subscriptions = FieldProperty({str: bool})
    first_post_id = ForeignIdProperty('Post')
    last_post_date = FieldProperty(datetime, if_missing=datetime(1970, 1, 1))
    artifact_reference = FieldProperty(schema.Deprecated)
    artifact_id = FieldProperty(schema.Deprecated)

    discussion = RelationProperty(Discussion)
    posts = RelationProperty('Post', via='thread_id')
    first_post = RelationProperty('Post', via='first_post_id')
    ref = RelationProperty('ArtifactReference')

    def should_update_index(self, old_doc, new_doc):
        """Skip index update if only `num_views` has changed.

        Value of `num_views` is updated whenever user loads thread page.
        This generates a lot of unnecessary `add_artifacts` tasks.
        """
        old_doc.pop('num_views', None)
        new_doc.pop('num_views', None)
        return old_doc != new_doc

    def attachment_for_export(self, page):
        return [dict(bytes=attach.length,
                     url=h.absurl(attach.url()),
                     path=os.path.join(
                         self.artifact.app_config.options.mount_point,
                         str(self.artifact._id),
                         self._id,
                         page.slug,
                         os.path.basename(attach.filename))
                     ) for attach in page.attachments]

    def attachments_for_json(self, page):
        return [dict(bytes=attach.length,
                     url=h.absurl(attach.url())) for attach in page.attachments]

    def __json__(self, limit=None, page=None, is_export=False):
        return dict(
            _id=self._id,
            discussion_id=str(self.discussion_id),
            subject=self.subject,
            limit=limit,
            page=page,
            posts=[dict(slug=p.slug,
                        text=p.text,
                        subject=p.subject,
                        author=p.author().username,
                        author_icon_url=h.absurl(p.author().icon_url()),
                        timestamp=p.timestamp,
                        last_edited=p.last_edit_date,
                        attachments=self.attachment_for_export(p) if is_export else self.attachments_for_json(p))
                   for p in self.query_posts(status='ok', style='chronological', limit=limit, page=page)
                   ]
        )

    @property
    def activity_name(self):
        return 'thread %s' % self.subject

    def parent_security_context(self):
        return self.discussion

    @classmethod
    def new(cls, **props):
        '''Creates a new Thread instance, ensuring a unique _id.'''
        for i in range(5):
            try:
                thread = cls(**props)
                session(thread).flush(thread)
                return thread
            except DuplicateKeyError as err:
                log.warning(
                    'Got DuplicateKeyError: attempt #%s, trying again. %s', i, err)
                if i == 4:
                    raise
                session(thread).expunge(thread)
                continue

    @classmethod
    def discussion_class(cls):
        return cls.discussion.related

    @classmethod
    def post_class(cls):
        return cls.posts.related

    @classmethod
    def attachment_class(cls):
        return DiscussionAttachment

    @property
    def artifact(self):
        # Threads attached to a wiki page, ticket, etc will have a .ref.artifact pointing to that WikiPage etc
        # Threads that are part of a forum will not have that
        if self.ref is None:
            return self.discussion
        return self.ref.artifact

    # Use wisely - there's .num_replies also
    @property
    def post_count(self):
        return Post.query.find(dict(
            discussion_id=self.discussion_id,
            thread_id=self._id,
            status={'$in': ['ok', 'pending']},
            deleted=False,
        )).count()

    def primary(self):
        if self.ref is None:
            return self
        return self.ref.artifact

    def post_to_feed(self, post):
        if post.status == 'ok':
            Feed.post(
                self.primary(),
                title=post.subject,
                description=post.text,
                link=post.url_paginated(),
                pubdate=post.mod_date,
            )

    def add_post(self, **kw):
        """Helper function to avoid code duplication."""
        p = self.post(**kw)
        p.commit(update_stats=False)
        session(self).flush(self)
        self.update_stats()
        if not self.first_post:
            self.first_post_id = p._id
        self.post_to_feed(p)
        return p

    def include_subject_in_spam_check(self, post):
        return (post.primary() == post  # only artifacts where the discussion is the main thing i.e. ForumPost
                and
                self.num_replies == 0)  # only first post in thread

    def is_spam(self, post):
        roles = [r.name for r in c.project.named_roles]
        spam_check_text = post.text
        if self.include_subject_in_spam_check(post):
            spam_check_text = self.subject + '\n' + spam_check_text
        spammy = g.spam_checker.check(spam_check_text, artifact=post, user=c.user)
        if c.user in c.project.users_with_role(*roles):
            # always run the check, so it's logged.  But don't act on it for admins/developers of their own project
            return False
        else:
            return spammy

    def post(self, text, message_id=None, parent_id=None, notify=True,
             notification_text=None, timestamp=None, ignore_security=False,
             is_meta=False, subscribe=False, **kw):
        if not ignore_security:
            require_access(self, 'post')
        if subscribe:
            self.primary().subscribe()
        if message_id is None:
            message_id = h.gen_message_id()
        parent = parent_id and self.post_class().query.get(_id=parent_id)
        slug, full_slug = self.post_class().make_slugs(parent, timestamp)
        kwargs = dict(
            discussion_id=self.discussion_id,
            full_slug=full_slug,
            slug=slug,
            thread_id=self._id,
            parent_id=parent_id,
            text=text,
            status='pending',
            is_meta=is_meta)
        if timestamp is not None:
            kwargs['timestamp'] = timestamp
        if message_id is not None:
            kwargs['_id'] = message_id
        post = self.post_class()(**kwargs)

        if ignore_security or is_meta:
            spammy = False
        else:
            spammy = self.is_spam(post)
        # unmoderated post -> autoapprove
        # unmoderated post but is spammy -> don't approve it, it goes into moderation
        # moderated post -> moderation
        # moderated post but is spammy -> mark as spam
        if ignore_security or (not spammy and has_access(self, 'unmoderated_post')):
            log.info('Auto-approving message from %s', c.user.username)
            file_info = kw.get('file_info', None)
            post.approve(file_info, notify=notify,
                         notification_text=notification_text)
        elif not has_access(self, 'unmoderated_post') and spammy:
            post.spam(submit_spam_feedback=False)  # no feedback since we're marking as spam automatically not manually
        else:
            self.notify_moderators(post)
        return post

    def notify_moderators(self, post):
        ''' Notify moderators that a post needs approval [#2963] '''
        artifact = self.artifact or self
        subject = '[{}:{}] Moderation action required'.format(
            c.project.shortname, c.app.config.options.mount_point)
        author = post.author()
        url = self.discussion_class().query.get(_id=self.discussion_id).url()
        text = ('The following submission requires approval at %s before '
                'it can be approved for posting:\n\n%s'
                % (h.absurl(url + 'moderate'), post.text))
        n = Notification(
            ref_id=artifact.index_id(),
            topic='message',
            link=artifact.url(),
            _id=artifact.url() + post._id,
            from_address=str(author._id) if author != User.anonymous()
            else None,
            reply_to_address=g.noreply,
            subject=subject,
            text=text,
            in_reply_to=post.parent_id,
            author_id=author._id,
            pubdate=datetime.utcnow())
        users = self.app_config.project.users()
        for u in users:
            if (has_access(self, 'moderate', u)
                and Mailbox.subscribed(user_id=u._id,
                                       app_config_id=post.app_config_id)):
                    n.send_direct(str(u._id))

    def update_stats(self):
        self.num_replies = self.post_class().query.find(
            dict(thread_id=self._id, status='ok', deleted=False)).count()

    @LazyProperty
    def last_post(self):
        q = self.post_class().query.find(dict(
            thread_id=self._id,
            deleted=False,
        )).sort('timestamp', pymongo.DESCENDING)
        return q.first()

    def create_post_threads(self, posts):
        result = []
        post_index = {}
        for p in sorted(posts, key=lambda p: p.full_slug):
            pi = dict(post=p, children=[])
            post_index[p._id] = pi
            if p.parent_id in post_index:
                post_index[p.parent_id]['children'].append(pi)
            else:
                result.append(pi)
        return result

    def query_posts(self, page=None, limit=None,
                    timestamp=None, style='threaded', status=None):
        if timestamp:
            terms = dict(discussion_id=self.discussion_id, thread_id=self._id,
                         status={'$in': ['ok', 'pending']}, timestamp=timestamp)
        else:
            terms = dict(discussion_id=self.discussion_id, thread_id=self._id,
                         status={'$in': ['ok', 'pending']})
        if status:
            terms['status'] = status
        terms['deleted'] = False
        q = self.post_class().query.find(terms)
        if style == 'threaded':
            q = q.sort('full_slug')
        else:
            q = q.sort('timestamp')
        if limit is not None:
            limit = int(limit)
            if page is not None:
                q = q.skip(page * limit)
            q = q.limit(limit)
        return q

    def find_posts(self, *args, **kwargs):
        return self.query_posts(*args, **kwargs).all()

    def url(self):
        # Can't use self.discussion because it might change during the req
        discussion = self.discussion_class().query.get(_id=self.discussion_id)
        return discussion.url() + 'thread/' + str(self._id) + '/'

    def shorthand_id(self):
        return self._id

    def index(self):
        result = Artifact.index(self)
        result.update(
            title=self.subject or '(no subject)',
            name_s=self.subject,
            views_i=self.num_views,
            text=self.subject)
        return result

    def delete(self):
        for p in self.post_class().query.find(dict(thread_id=self._id)):
            p.delete()
        self.attachment_class().remove(dict(thread_id=self._id))
        super().delete()

    def spam(self):
        """Mark this thread as spam."""
        for p in self.post_class().query.find(dict(thread_id=self._id)):
            p.spam()


class PostHistory(Snapshot):

    class __mongometa__:
        name = 'post_history'

    query: 'Query[PostHistory]'

    artifact_id = ForeignIdProperty('Post')

    @classmethod
    def post_class(cls):
        return cls.artifact_id.related

    def original(self):
        return self.post_class().query.get(_id=self.artifact_id)

    def shorthand_id(self):
        original = self.original()
        if original:
            return f'{original.shorthand_id()}#{self.version}'
        else:
            return None

    def url(self):
        if self.original():
            return self.original().url() + '?version=%d' % self.version
        else:
            return None

    def index(self):
        result = Snapshot.index(self)
        result.update(
            type_s='Post Snapshot',
            text=self.data.text)
        return result


class Post(Message, VersionedArtifact, ActivityObject, ReactableArtifact):

    class __mongometa__:
        name = 'post'
        history_class = PostHistory
        indexes = [
            # used in general lookups, last_post, etc
            ('discussion_id', 'status', 'timestamp'),
            # for update_stats()
            ('discussion_id', 'deleted', 'status'),
            # for update_stats() and thread_id in general
            ('thread_id', 'status', 'deleted'),
            # for find_posts/query_posts, including full_slug sort which is useful on super big threads
            ('deleted', 'discussion_id', 'thread_id', 'full_slug'),
        ]

    query: 'Query[Post]'

    type_s = 'Post'

    thread_id = ForeignIdProperty(Thread)
    discussion_id = ForeignIdProperty(Discussion)
    subject = FieldProperty(schema.Deprecated)
    status = FieldProperty(schema.OneOf('ok', 'pending', 'spam',
                                        if_missing='pending'))
    last_edit_date = FieldProperty(datetime, if_missing=None)
    last_edit_by_id: ObjectId = AlluraUserProperty()
    edit_count = FieldProperty(int, if_missing=0)
    spam_check_id = FieldProperty(str, if_missing='')
    text_cache = FieldProperty(MarkdownCache)
    # meta comment - system generated, describes changes to an artifact
    is_meta = FieldProperty(bool, if_missing=False)

    thread = RelationProperty(Thread)
    discussion = RelationProperty(Discussion)

    def __json__(self):
        author = self.author()
        return dict(
            _id=str(self._id),
            thread_id=self.thread_id,
            slug=self.slug,
            subject=self.subject,
            status=self.status,
            text=self.text,
            timestamp=self.timestamp,
            last_edited=self.last_edit_date,
            author_id=str(author._id),
            author=author.username)

    @property
    def activity_name(self):
        return 'a comment'

    @property
    def activity_url(self):
        return self.url_paginated()

    def has_activity_access(self, perm, user, activity):
        """Return True if user has perm access to this object, otherwise
        return False.

        For the purposes of activitystreams, we're saying that the user does
        not have access to a 'comment' activity unless he also has access to
        the artifact on which it was posted (if there is one).
        """
        if self.project is None or self.deleted or self.status != 'ok':
            return False
        artifact_access = True
        if self.thread.artifact:
            if self.thread.artifact.project is None:
                return False
            if self.thread.artifact.deleted:
                return False
            artifact_access = security.has_access(self.thread.artifact, perm,
                                                  user, self.thread.artifact.project)

        return artifact_access and security.has_access(self, perm, user,
                                                       self.project)

    @property
    def activity_extras(self):
        d = ActivityObject.activity_extras.fget(self)
        # For activity summary, convert Post text to html,
        # strip all tags, and truncate
        LEN = 500
        summary = markupsafe.Markup.escape(
            g.markdown.cached_convert(self, 'text')).striptags()
        if len(summary) > LEN:
            split = max(summary.find(' ', LEN), LEN)
            summary = summary[:split] + '...'
        d.update(summary=summary)
        return d

    def index(self):
        result = super().index()
        result.update(
            title='Post by {} on {}'.format(
                self.author().username, self.subject),
            name_s=self.subject,
            type_s='Post',
            text=self.text)
        return result

    @classmethod
    def discussion_class(cls):
        return cls.discussion.related

    @classmethod
    def thread_class(cls):
        return cls.thread.related

    @classmethod
    def attachment_class(cls):
        return DiscussionAttachment

    @property
    def parent(self):
        if self.parent_id:
            return self.query.get(_id=self.parent_id)

    @property
    def subject(self):
        subject = None
        if self.thread:
            subject = self.thread.subject
            if not subject:
                artifact = self.thread.artifact
                if artifact:
                    subject = getattr(artifact, 'email_subject', '')
        return subject or '(no subject)'

    def add_multiple_attachments(self, file_info):
        if isinstance(file_info, list):
            for fi in file_info:
                self.add_attachment(fi)
        else:
            self.add_attachment(file_info)

    def add_attachment(self, file_info):
        if hasattr(file_info, 'file'):
            mime_type = file_info.type
            if not mime_type or '/' not in mime_type:
                mime_type = utils.guess_mime_type(file_info.filename)
            self.attach(
                file_info.filename, file_info.file, content_type=mime_type,
                post_id=self._id,
                thread_id=self.thread_id,
                discussion_id=self.discussion_id)

    def last_edit_by(self):
        return User.query.get(_id=self.last_edit_by_id) or User.anonymous()

    def primary(self):
        return self.thread.primary()

    def url(self):
        if self.thread:
            return self.thread.url() + h.urlquote(self.slug) + '/'
        else:  # pragma no cover
            return None

    def parent_artifact(self):
        """
        :return: the artifact (e.g Ticket, Wiki Page) that this Post belongs to.  May return None.
        """
        aref = ArtifactReference.query.get(_id=self.thread.ref_id)
        if aref and aref.artifact:
            return aref.artifact
        else:
            return None

    def main_url(self):
        """
        :return: the URL for the artifact (e.g Ticket, Wiki Page) that this Post belongs to,
                 else the default thread URL
        """
        parent_artifact = self.parent_artifact()
        if parent_artifact:
            url = parent_artifact.url()
        else:
            url = self.thread.url()
        return url

    def url_paginated(self):
        '''Return link to the thread with a #target that poins to this comment.

        Also handle pagination properly.
        '''
        if not self.thread:  # pragma no cover
            return None
        limit, p, s = g.handle_paging(None, 0)  # get paging limit
        if self.query.find(dict(thread_id=self.thread._id)).count() <= limit:
            # all posts in a single page
            page = 0
        else:
            posts = self.thread.find_posts()
            posts = self.thread.create_post_threads(posts)

            def find_i(posts):
                '''Find the index number of this post in the display order'''
                q = []

                def traverse(posts):
                    for p in posts:
                        if p['post']._id == self._id:
                            return True  # found
                        q.append(p)
                        if traverse(p['children']):
                            return True
                traverse(posts)
                return len(q)

            page = find_i(posts) // limit

        slug = h.urlquote(self.slug)
        url = self.main_url()
        if page == 0:
            return f'{url}?limit={limit}#{slug}'
        return f'{url}?limit={limit}&page={page}#{slug}'

    def shorthand_id(self):
        if self.thread:
            return f'{self.thread.shorthand_id()}#{self.slug}'
        else:  # pragma no cover
            return None

    def link_text(self):
        return self.subject

    def reply_subject(self):
        if self.subject and self.subject.lower().startswith('re:'):
            return self.subject
        else:
            return 'Re: ' + (self.subject or '(no subject)')

    def delete(self):
        self.deleted = True
        session(self).flush(self)
        self.thread.update_stats()

    def approve(self, file_info=None, notify=True, notification_text=None):
        if self.status == 'ok':
            return
        self.status = 'ok'
        author = self.author()
        author_role = ProjectRole.by_user(
            author, project=self.project, upsert=True)
        if not author.is_anonymous():
            security.simple_grant(
                self.acl, author_role._id, 'moderate')
        self.commit()
        if (c.app.config.options.get('PostingPolicy') == 'ApproveOnceModerated'
                and author._id is not None):
            security.simple_grant(
                self.acl, author_role._id, 'unmoderated_post')
        if notify:
            self.notify(file_info=file_info, notification_text=notification_text)
        artifact = self.thread.artifact or self.thread
        session(self).flush()
        self.thread.last_post_date = max(
            self.thread.last_post_date,
            self.mod_date)
        self.thread.update_stats()
        if hasattr(artifact, 'update_stats'):
            artifact.update_stats()
        if self.text and not self.is_meta:
            g.director.create_activity(author, 'posted', self, target=artifact,
                                       related_nodes=[self.app_config.project],
                                       tags=['comment'])

    def notify(self, file_info=None, notification_text=None):
        if self.project.notifications_disabled:
            return  # notifications disabled for entire project
        artifact = self.thread.artifact or self.thread
        msg_id = artifact.url() + self._id
        notification_params = dict(
            post=self,
            text=notification_text,
            file_info=file_info)
        n = Notification.query.get(_id=msg_id)
        if n and 'Moderation action required' in n.subject:
            # Existing notification for this artifact is for moderators only,
            # this means artifact was not auto approved, and all the
            # subscribers did not receive notification. Now, moderator approved
            # artifact/post, so we should re-send actual notification
            msg_id = 'approved-' + msg_id
            n = Notification.query.get(_id=msg_id)
            if n:
                # 'approved' notification also exists, re-send
                n.fire_notification_task([artifact, self.thread], 'message')
            else:
                # 'approved' notification does not exist, create
                notification_params['message_id'] = msg_id
        if not n:
            # artifact is Forum (or artifact like WikiPage)
            n = Notification.post(artifact, 'message',
                                  additional_artifacts_to_match_subscriptions=self.thread,
                                  **notification_params)
        if not n:
            return
        if getattr(artifact, 'monitoring_email', None):
            if hasattr(artifact, 'notify_post'):
                if artifact.notify_post:
                    n.send_simple(artifact.monitoring_email)
            else:  # Send if no extra checks required
                n.send_simple(artifact.monitoring_email)

    def spam(self, submit_spam_feedback=True):
        self.status = 'spam'
        if submit_spam_feedback:
            g.spam_checker.submit_spam(self.text, artifact=self, user=self.author())
        session(self).flush(self)
        self.thread.update_stats()

    def undo(self, prev_status):
        if prev_status in ('ok', 'pending'):
            self.status = prev_status
            session(self).flush(self)
            self.thread.update_stats()


class DiscussionAttachment(BaseAttachment):
    DiscussionClass = Discussion
    ThreadClass = Thread
    PostClass = Post
    ArtifactClass = Post
    thumbnail_size = (100, 100)

    class __mongometa__:
        polymorphic_identity = 'DiscussionAttachment'
        indexes = ['filename', 'discussion_id', 'thread_id', 'post_id']

    query: 'Query[DiscussionAttachment]'

    discussion_id = FieldProperty(schema.ObjectId)
    thread_id = FieldProperty(str)
    post_id = FieldProperty(str)
    artifact_id = FieldProperty(str)
    attachment_type = FieldProperty(str, if_missing='DiscussionAttachment')

    @property
    def discussion(self):
        return self.DiscussionClass.query.get(_id=self.discussion_id)

    @property
    def thread(self):
        return self.ThreadClass.query.get(_id=self.thread_id)

    @property
    def post(self):
        return self.PostClass.query.get(_id=self.post_id)

    @classmethod
    def metadata_for(cls, post):
        return dict(
            post_id=post._id,
            thread_id=post.thread_id,
            discussion_id=post.discussion_id,
            app_config_id=post.app_config_id)

    def url(self):
        if self.post_id:
            return (self.post.url() + 'attachment/' +
                    h.urlquote(self.filename))
        elif self.thread_id:
            return (self.thread.url() + 'attachment/' +
                    h.urlquote(self.filename))
        else:
            return (self.discussion.url() + 'attachment/' +
                    h.urlquote(self.filename))
