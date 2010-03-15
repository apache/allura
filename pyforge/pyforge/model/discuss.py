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

from pyforge.lib.helpers import nonce, ago
from pyforge.lib.security import require, has_artifact_access
from .artifact import Artifact, VersionedArtifact, Snapshot, Message, gen_message_id
from .filesystem import File

log = logging.getLogger(__name__)

common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')

class Discussion(Artifact):
    class __mongometa__:
        name='discussion'
    type_s = 'Discussion'

    shortname = FieldProperty(str)
    name = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    num_topics = FieldProperty(int, if_missing=0)
    num_posts = FieldProperty(int, if_missing=0)
    subscriptions = FieldProperty({str:bool})

    threads = RelationProperty('Thread')
    posts = RelationProperty('Post')

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
        result.update(name_s=self.name,
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

    _id=FieldProperty(str, if_missing=lambda:nonce(8))
    discussion_id = ForeignIdProperty(Discussion)
    artifact_id = ForeignIdProperty(Artifact, if_missing=None)
    subject = FieldProperty(str)
    num_replies = FieldProperty(int, if_missing=0)
    num_views = FieldProperty(int, if_missing=0)
    subscriptions = FieldProperty({str:bool})
    first_post_id = ForeignIdProperty('Post')

    discussion = RelationProperty(Discussion)
    posts = RelationProperty('Post', via='thread_id')
    first_post = RelationProperty('Post', via='first_post_id')

    @classmethod
    def discussion_class(cls):
        return cls.discussion.related

    @classmethod
    def post_class(cls):
        return cls.posts.related

    @classmethod
    def attachment_class(cls):
        return Attachment

    def primary(self, primary_class=None):
        result = primary_class.query.get(_id=self.artifact_id)
        if result is None: return self
        return result

    def post(self, text, message_id=None, parent_id=None, **kw):
        require(has_artifact_access('post', self))
        if message_id is None: message_id = gen_message_id()
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

    def find_posts(self, offset=None, limit=None, style='threaded'):
        q = self.post_class().query.find(
            dict(discussion_id=self.discussion_id, thread_id=self._id, status='ok'))
        if style == 'threaded':
            q = q.sort('full_slug')
        else:
            q = q.sort('timestamp')
        if offset is not None:
            q = q.skip(offset)
        if limit is not None:
            q = q.limit(limit)
        q = q.all()
        return q

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
        result.update(name_s=self.subject,
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
        return primary_class.query.get(_id=self.thread.artifact_id)

    def summary(self):
        return '<a href="%s">%s</a> %s' % (
            self.author().url(), self.author().display_name,
            ago(self.timestamp))

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
            return 'Re: ' + self.subject

    def reply_text(self):
        if self.text:
            l = [ '%s wrote:' % self.author().display_name ]
            l += [ '> ' + line for line in self.text.split('\n') ]
        else:
            return ''
        return '\n'.join(l)

    def delete(self):
        for att in self.attachment_class().by_metadata(post_id=self._id):
            att.delete()
        super(Post, self).delete()

    def approve(self):
        self.status = 'ok'
        if self.parent_id is None:
            thd = self.thread_class().query.get(_id=self.thread_id)
            g.publish('react', 'Discussion.new_thread', dict(thread_id=thd._id))
        self.give_access('moderate', user=self.author())
        self.commit()
        if c.app.config.options.get('PostingPolicy') == 'ApproveOnceModerated':
            c.app.config.grant_permission('unmoderated_post', self.author())
        g.publish('react', 'Discussion.new_post', dict(post_id=self._id))
        session(self).flush()
        self.thread.update_stats()
        self.discussion.update_stats()

    def spam(self):
        self.status = 'spam'
        g.publish('react', 'spam', dict(artifact_reference=self.dump_ref()),
                  serializer='pickle')

class Attachment(File):
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


