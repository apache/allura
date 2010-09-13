import re
import logging

import tg
import pymongo
from pylons import c, g, request
from pymongo.bson import ObjectId

from ming import schema
from ming.orm.base import mapper, session
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, RelationProperty, ForeignIdProperty

from allura.lib import helpers as h
from allura.lib.security import require, has_artifact_access
from .auth import ProjectRole
from .artifact import Artifact, VersionedArtifact, Snapshot, Message, Feed, BaseAttachment
from .types import ArtifactReference, ArtifactReferenceType

log = logging.getLogger(__name__)

common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')

class Discussion(Artifact):
    class __mongometa__:
        name='discussion'
    type_s = 'Discussion'

    parent_id = FieldProperty(schema.Deprecated)
    shortname = FieldProperty(str)
    name = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    num_topics = FieldProperty(int, if_missing=0)
    num_posts = FieldProperty(int, if_missing=0)
    subscriptions = FieldProperty({str:bool})

    threads = RelationProperty('Thread')
    posts = RelationProperty('Post')

    def __json__(self):
        return dict(
            _id=str(self._id),
            shortname=self.shortname,
            name=self.name,
            description=self.description,
            threads=[dict(_id=t._id, subject=t.subject)
                     for t in self.threads ])

    @classmethod
    def thread_class(cls):
        return cls.threads.related

    @classmethod
    def post_class(cls):
        return cls.posts.related

    @classmethod
    def attachment_class(cls):
        return Attachment

    def update_stats(self):
        self.num_topics = self.thread_class().query.find(
            dict(discussion_id=self._id)).count()
        self.num_posts = self.post_class().query.find(
            dict(discussion_id=self._id, status='ok')).count()

    @property
    def last_post(self):
        q = self.post_class().query.find(dict(
                discussion_id=self._id)).sort('timestamp', pymongo.DESCENDING)
        return q.first()

    def url(self):
        return self.app.url + '_discuss/'

    def shorthand_id(self):
        return self.shortname

    def index(self):
        result = Artifact.index(self)
        result.update(
            title_s='Discussion: %s' % self.name,
            name_s=self.name,
            text=self.description)
        return result

    def subscription(self):
        return self.subscriptions.get(str(c.user._id))

    def delete(self):
        # Delete all the threads, posts, and artifacts
        self.thread_class().query.remove(dict(discussion_id=self._id))
        self.post_class().query.remove(dict(discussion_id=self._id))
        for att in self.attachment_class().by_metadata(discussion_id=self._id):
            att.delete()
        super(Discussion, self).delete()

    def find_posts(self, **kw):
        q = dict(kw, discussion_id=self._id)
        return self.post_class().query.find(q)

class Thread(Artifact):
    class __mongometa__:
        name='thread'
    type_s = 'Thread'

    _id=FieldProperty(str, if_missing=lambda:h.nonce(8))
    discussion_id = ForeignIdProperty(Discussion)
    artifact_id = FieldProperty(None)
    artifact_reference = FieldProperty(ArtifactReferenceType)
    subject = FieldProperty(str, if_missing='(no subject)')
    num_replies = FieldProperty(int, if_missing=0)
    num_views = FieldProperty(int, if_missing=0)
    subscriptions = FieldProperty({str:bool})
    first_post_id = ForeignIdProperty('Post')

    discussion = RelationProperty(Discussion)
    posts = RelationProperty('Post', via='thread_id')
    first_post = RelationProperty('Post', via='first_post_id')

    def __json__(self):
        return dict(
            _id=self._id,
            discussion_id=str(self.discussion_id),
            subject=self.subject,
            posts=[dict(slug=p.slug, subject=p.subject)
                   for p in self.posts ])

    @classmethod
    def discussion_class(cls):
        return cls.discussion.related

    @classmethod
    def post_class(cls):
        return cls.posts.related

    @classmethod
    def attachment_class(cls):
        return Attachment

    @property
    def artifact(self):
        aref = ArtifactReference(self.artifact_reference)
        if aref is None: return self.discussion
        return aref.artifact

    def primary(self, primary_class=None):
        result = primary_class.query.get(_id=self.artifact_reference.artifact_id)
        if result is None: return self
        return result

    def add_post(self, **kw):
        """Helper function to avoid code duplication."""
        p = self.post(**kw)
        p.commit()
        self.num_replies += 1
        if not self.first_post:
            self.first_post_id = p._id
        Feed.post(self, title=p.subject, description=p.text)
        return p

    def post(self, text, message_id=None, parent_id=None, **kw):
        require(has_artifact_access('post', self))
        if self.artifact_reference.artifact_id is not None:
            if self.artifact:
                self.artifact.subscribe()
        if message_id is None: message_id = h.gen_message_id()
        parent = parent_id and self.post_class().query.get(_id=parent_id)
        slug, full_slug = self.post_class().make_slugs(parent)
        kwargs = dict(
            discussion_id=self.discussion_id,
            full_slug=full_slug,
            slug=slug,
            thread_id=self._id,
            parent_id=parent_id,
            text=text,
            status='pending')
        if message_id is not None: kwargs['_id'] = message_id
        post = self.post_class()(**kwargs)
        if has_artifact_access('unmoderated_post')():
            log.info('Auto-approving message from %s', c.user.username)
            post.approve()
        return post

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
        for p in sorted(posts, key=lambda p:p.full_slug):
            pi = dict(post=p, children=[])
            post_index[p._id] = pi
            if p.parent_id in post_index:
                post_index[p.parent_id]['children'].append(pi)
            else:
                result.append(pi)
        return result

    def query_posts(self, page=None, limit=None, timestamp=None, style='threaded'):
        if limit is None:
            limit = 25
        limit = int(limit)
        if timestamp:
            terms = dict(discussion_id=self.discussion_id, thread_id=self._id,
                    status='ok', timestamp=timestamp)
        else:
            terms = dict(discussion_id=self.discussion_id, thread_id=self._id,
                    status='ok')
        q = self.post_class().query.find(terms)
        if style == 'threaded':
            q = q.sort('full_slug')
        else:
            q = q.sort('timestamp')
        if page is not None:
            q = q.skip(page*limit)
        if limit is not None:
            q = q.limit(limit)
        return q

    def find_posts(self, page=None, limit=None, timestamp=None, style='threaded'):
        return self.query_posts(page=page, limit=limit, timestamp=timestamp, style=style).all()

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
           title_s='Thread: %s' % (self.subject or '(no subject)'),
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
    subscription=property(_get_subscription, _set_subscription)

    def delete(self):
        self.post_class().query.remove(dict(thread_id=self._id))
        for att in self.attachment_class().by_metadata(thread_id=self._id):
            att.delete()
        super(Thread, self).delete()

class PostHistory(Snapshot):
    class __mongometa__:
        name='post_history'

    artifact_id = ForeignIdProperty('Post')

    @classmethod
    def post_class(cls):
        return cls.artifact_id.related

    def original(self):
        return self.post_class().query.get(_id=self.artifact_id)

    def shorthand_id(self):
        return '%s#%s' % (self.original().shorthand_id(), self.version)

    def url(self):
        return self.original().url() + '?version=%d' % self.version

    def index(self):
        result = Snapshot.index(self)
        result.update(
            title_s='Version %d of %s' % (
                self.version,self.original().subject),
            type_s='Post Snapshot',
            text=self.data.text)
        return result

class Post(Message, VersionedArtifact):
    class __mongometa__:
        name='post'
        history_class = PostHistory
    type_s = 'Post'

    thread_id = ForeignIdProperty(Thread)
    discussion_id = ForeignIdProperty(Discussion)
    subject = FieldProperty(schema.Deprecated)
    status = FieldProperty(schema.OneOf('ok', 'pending', 'spam', if_missing='pending'))
    flagged_by = FieldProperty([schema.ObjectId])
    flags = FieldProperty(int, if_missing=0)

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

    def index(self):
        result = super(Post, self).index()
        result.update(
            title_s='Post by %s on %s' % (
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
        return Attachment

    @property
    def parent(self):
        return self.query.get(_id=self.parent_id)

    @property
    def subject(self):
        return self.thread.subject

    @property
    def attachments(self):
        return self.attachment_class().by_metadata(post_id=self._id)

    def primary(self, primary_class=None):
        return self.thread.primary(primary_class)

    def summary(self):
        return '<a href="%s">%s</a> %s' % (
            self.author().url(), self.author().display_name,
            h.ago(self.timestamp))

    def url(self):
        if self.thread:
            return self.thread.url() + self.slug + '/'
        else: # pragma no cover
            return None

    def shorthand_id(self):
        if self.thread:
            return '%s#%s' % (self.thread.shorthand_id(), self.slug)
        else: # pragma no cover
            return None

    def reply_subject(self):
        if self.subject.lower().startswith('re:'):
            return self.subject
        else:
            return 'Re: ' +(self.subject or '(no subject)')

    def delete(self):
        for att in self.attachment_class().by_metadata(post_id=self._id):
            att.delete()
        super(Post, self).delete()

    def approve(self):
        from allura.model.notification import Notification
        if self.status == 'ok': return
        self.status = 'ok'
        if self.parent_id is None:
            thd = self.thread_class().query.get(_id=self.thread_id)
            g.publish('react', 'Discussion.new_thread', dict(thread_id=thd._id))
        self.give_access('moderate', user=self.author())
        self.commit()
        author = self.author()
        if (c.app.config.options.get('PostingPolicy') == 'ApproveOnceModerated'
            and author._id != None):
            c.app.config.grant_permission('unmoderated_post', author)
        g.publish('react', 'Discussion.new_post', dict(post_id=self._id))
        artifact = self.thread.artifact or self.thread
        Notification.post(artifact, 'message', post=self)
        session(self).flush()
        self.thread.update_stats()
        self.discussion.update_stats()

    def spam(self):
        self.status = 'spam'
        g.publish('react', 'spam', dict(artifact_reference=self.dump_ref()),
                  serializer='pickle')

class Attachment(BaseAttachment):
    DiscussionClass=Discussion
    ThreadClass=Thread
    PostClass=Post
    class __mongometa__:
        name = 'attachment.files'
        indexes = [
            'metadata.filename',
            'metadata.discussion_id',
            'metadata.thread_id',
            'metadata.post_id' ]

    # Override the metadata schema here
    metadata=FieldProperty(dict(
            discussion_id=schema.ObjectId,
            thread_id=str,
            post_id=str,
            filename=str))

    @property
    def discussion(self):
        return self.DiscussionClass.query.get(_id=self.metadata.discussion_id)

    @property
    def thread(self):
        return self.ThreadClass.query.get(_id=self.metadata.thread_id)

    @property
    def post(self):
        return self.PostClass.query.get(_id=self.metadata.post_id)

    def url(self):
        return self.discussion.url() + 'attachment/' + self.filename


