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
from datetime import datetime

import pymongo
from pymongo.errors import DuplicateKeyError
from pylons import tmpl_context as c, app_globals as g

from ming import schema
from ming.orm.base import session
from ming.orm.property import (FieldProperty, RelationProperty,
                               ForeignIdProperty)
from ming.utils import LazyProperty

from allura.lib import helpers as h
from allura.lib import security
from allura.lib.security import require_access, has_access
from allura.model.notification import Notification, Mailbox
from .artifact import Artifact, ArtifactReference, VersionedArtifact, Snapshot, Message, Feed
from .attachments import BaseAttachment
from .auth import User
from .timeline import ActivityObject

log = logging.getLogger(__name__)


class Discussion(Artifact, ActivityObject):
    class __mongometa__:
        name = 'discussion'
    type_s = 'Discussion'

    parent_id = FieldProperty(schema.Deprecated)
    shortname = FieldProperty(str)
    name = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    num_topics = FieldProperty(int, if_missing=0)
    num_posts = FieldProperty(int, if_missing=0)
    subscriptions = FieldProperty({str: bool})

    threads = RelationProperty('Thread')
    posts = RelationProperty('Post')

    def __json__(self):
        return dict(
            _id=str(self._id),
            shortname=self.shortname,
            name=self.name,
            description=self.description,
            threads=[dict(_id=t._id, subject=t.subject)
                     for t in self.threads])

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
            dict(discussion_id=self._id, status='ok')).count()

    @LazyProperty
    def last_post(self):
        q = self.post_class().query.find(dict(
                discussion_id=self._id))\
            .sort('timestamp', pymongo.DESCENDING)\
            .limit(1)\
            .hint([('discussion_id', pymongo.ASCENDING)])
            # hint is to try to force the index to be used, since mongo wouldn't select it sometimes
            # https://groups.google.com/forum/#!topic/mongodb-user/0TEqPfXxQU8
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

    def subscription(self):
        return self.subscriptions.get(str(c.user._id))

    def delete(self):
        # Delete all the threads, posts, and artifacts
        self.thread_class().query.remove(dict(discussion_id=self._id))
        self.post_class().query.remove(dict(discussion_id=self._id))
        self.attachment_class().remove(dict(discussion_id=self._id))
        super(Discussion, self).delete()

    def find_posts(self, **kw):
        q = dict(kw, discussion_id=self._id)
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
    type_s = 'Thread'

    _id = FieldProperty(str, if_missing=lambda: h.nonce(8))
    discussion_id = ForeignIdProperty(Discussion)
    ref_id = ForeignIdProperty('ArtifactReference')
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

    def __json__(self):
        return dict(
            _id=self._id,
            discussion_id=str(self.discussion_id),
            subject=self.subject,
            posts=[dict(slug=p.slug, subject=p.subject)
                   for p in self.posts])

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
                log.warning('Got DuplicateKeyError: attempt #%s, trying again. %s', i, err)
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
        if self.ref is None:
            return self.discussion
        return self.ref.artifact

    # Use wisely - there's .num_replies also
    @property
    def post_count(self):
        return Post.query.find(dict(
                discussion_id=self.discussion_id,
                thread_id=self._id)).count()

    def primary(self):
        if self.ref is None:
            return self
        return self.ref.artifact

    def add_post(self, **kw):
        """Helper function to avoid code duplication."""
        p = self.post(**kw)
        p.commit(update_stats=False)
        self.num_replies += 1
        if not self.first_post:
            self.first_post_id = p._id
        link = None
        if self.app.tool_label == 'Tickets':
            link = self.artifact.url() + p.url_paginated()[len(self.url()):]
        if self.ref:
            Feed.post(self.primary(), title=p.subject, description=p.text, link=link)
        return p

    def post(self, text, message_id=None, parent_id=None,
             timestamp=None, ignore_security=False, **kw):
        if not ignore_security:
            require_access(self, 'post')
        if self.ref_id and self.artifact:
            self.artifact.subscribe()
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
            status='pending')
        if timestamp is not None:
            kwargs['timestamp'] = timestamp
        if message_id is not None:
            kwargs['_id'] = message_id
        post = self.post_class()(**kwargs)
        if ignore_security or has_access(self, 'unmoderated_post')():
            log.info('Auto-approving message from %s', c.user.username)
            file_info = kw.get('file_info', None)
            post.approve(file_info, notify=kw.get('notify', True))
        else:
            self.notify_moderators(post)
        return post

    def notify_moderators(self, post):
        ''' Notify moderators that a post needs approval [#2963] '''
        artifact = self.artifact or self
        subject = '[%s:%s] Moderation action required' % (
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
                reply_to_address=u'noreply@in.sf.net',
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
            dict(thread_id=self._id, status='ok')).count() - 1

    @property
    def last_post(self):
        q = self.post_class().query.find(dict(
                thread_id=self._id)).sort('timestamp', pymongo.DESCENDING)
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
                    timestamp=None, style='threaded'):
        if timestamp:
            terms = dict(discussion_id=self.discussion_id, thread_id=self._id,
                    status={'$in': ['ok', 'pending']}, timestamp=timestamp)
        else:
            terms = dict(discussion_id=self.discussion_id, thread_id=self._id,
                    status={'$in': ['ok', 'pending']})
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

    def find_posts(self, page=None, limit=None, timestamp=None,
                   style='threaded'):
        return self.query_posts(page=page, limit=limit,
                                timestamp=timestamp, style=style).all()

    def top_level_posts(self):
        return self.post_class().query.find(dict(
                thread_id=self._id,
                parent_id=None,
                status='ok'))

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

    def _get_subscription(self):
        return self.subscriptions.get(str(c.user._id))

    def _set_subscription(self, value):
        if value:
            self.subscriptions[str(c.user._id)] = True
        else:
            self.subscriptions.pop(str(c.user._id), None)
    subscription = property(_get_subscription, _set_subscription)

    def delete(self):
        for p in self.post_class().query.find(dict(thread_id=self._id)):
            p.delete()
        self.attachment_class().remove(dict(thread_id=self._id))
        super(Thread, self).delete()

    def spam(self):
        """Mark this thread as spam."""
        for p in self.post_class().query.find(dict(thread_id=self._id)):
            p.spam()


class PostHistory(Snapshot):
    class __mongometa__:
        name = 'post_history'

    artifact_id = ForeignIdProperty('Post')

    @classmethod
    def post_class(cls):
        return cls.artifact_id.related

    def original(self):
        return self.post_class().query.get(_id=self.artifact_id)

    def shorthand_id(self):
        original = self.original()
        if original:
            return '%s#%s' % (original.shorthand_id(), self.version)
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


class Post(Message, VersionedArtifact, ActivityObject):
    class __mongometa__:
        name = 'post'
        history_class = PostHistory
        indexes = ['discussion_id', 'thread_id']
    type_s = 'Post'

    thread_id = ForeignIdProperty(Thread)
    discussion_id = ForeignIdProperty(Discussion)
    subject = FieldProperty(schema.Deprecated)
    status = FieldProperty(schema.OneOf('ok', 'pending', 'spam',
                                        if_missing='pending'))
    flagged_by = FieldProperty([schema.ObjectId])
    flags = FieldProperty(int, if_missing=0)
    last_edit_date = FieldProperty(datetime, if_missing=None)
    last_edit_by_id = ForeignIdProperty(User)
    edit_count = FieldProperty(int, if_missing=0)

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
            flagged_by=map(str, self.flagged_by),
            timestamp=self.timestamp,
            author_id=str(author._id),
            author=author.username)

    @property
    def activity_name(self):
        return 'a comment'

    def has_activity_access(self, perm, user):
        """Return True if user has perm access to this object, otherwise
        return False.

        For the purposes of activitystreams, we're saying that the user does
        not have access to a 'comment' activity unless he also has access to
        the artifact on which it was posted (if there is one).
        """
        artifact_access = True
        if self.thread.artifact:
            artifact_access = security.has_access(self.thread.artifact, perm,
                    user, self.thread.artifact.project)

        return artifact_access and security.has_access(self, perm, user,
                self.project)

    def index(self):
        result = super(Post, self).index()
        result.update(
            title='Post by %s on %s' % (
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
        return self.query.get(_id=self.parent_id)

    @property
    def subject(self):
        subject = self.thread.subject
        if not subject:
            artifact = self.thread.artifact
            if artifact:
                subject = getattr(artifact, 'email_subject', '')
        return subject or '(no subject)'

    @property
    def attachments(self):
        return self.attachment_class().query.find(dict(
            post_id=self._id, type='attachment'))

    def last_edit_by(self):
        return User.query.get(_id=self.last_edit_by_id) or User.anonymous()

    def primary(self):
        return self.thread.primary()

    def url(self):
        if self.thread:
            return self.thread.url() + h.urlquote(self.slug) + '/'
        else:  # pragma no cover
            return None

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

            page = find_i(posts) / limit

        slug = h.urlquote(self.slug)
        aref = ArtifactReference.query.get(_id=self.thread.ref_id)
        if aref and aref.artifact:
            url = aref.artifact.url()
        else:
            url = self.thread.url()
        if page == 0:
            return '%s?limit=%s#%s' % (url, limit, slug)
        return '%s?limit=%s&page=%s#%s' % (url, limit, page, slug)


    def shorthand_id(self):
        if self.thread:
            return '%s#%s' % (self.thread.shorthand_id(), self.slug)
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
        self.attachment_class().remove(dict(post_id=self._id))
        super(Post, self).delete()
        self.thread.num_replies = max(0, self.thread.num_replies - 1)

    def approve(self, file_info=None, notify=True):
        if self.status == 'ok':
            return
        self.status = 'ok'
        author = self.author()
        security.simple_grant(
            self.acl, author.project_role()._id, 'moderate')
        self.commit()
        if (c.app.config.options.get('PostingPolicy') == 'ApproveOnceModerated'
            and author._id != None):
            security.simple_grant(
                self.acl, author.project_role()._id, 'unmoderated_post')
        if notify:
            self.notify(file_info=file_info)
        artifact = self.thread.artifact or self.thread
        session(self).flush()
        self.thread.last_post_date = max(
            self.thread.last_post_date,
            self.mod_date)
        self.thread.update_stats()
        if hasattr(artifact, 'update_stats'):
            artifact.update_stats()
        if self.text:
            g.director.create_activity(author, 'posted', self, target=artifact,
                    related_nodes=[self.app_config.project])

    def notify(self, file_info=None, check_dup=False):
        if self.project.notifications_disabled:
            return  # notifications disabled for entire project
        artifact = self.thread.artifact or self.thread
        n = Notification.query.get(
            _id=artifact.url() + self._id) if check_dup else None
        if not n:
            n = Notification.post(artifact, 'message', post=self,
                                  file_info=file_info)
        if not n: return
        if (hasattr(artifact, "monitoring_email")
                and artifact.monitoring_email):
            if hasattr(artifact, 'notify_post'):
                if artifact.notify_post:
                    n.send_simple(artifact.monitoring_email)
            else:  # Send if no extra checks required
                n.send_simple(artifact.monitoring_email)

    def spam(self):
        self.status = 'spam'
        self.thread.num_replies = max(0, self.thread.num_replies - 1)


class DiscussionAttachment(BaseAttachment):
    DiscussionClass = Discussion
    ThreadClass = Thread
    PostClass = Post
    ArtifactClass = Post
    thumbnail_size = (100, 100)

    class __mongometa__:
        polymorphic_identity = 'DiscussionAttachment'
        indexes = ['filename', 'discussion_id', 'thread_id', 'post_id']

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
