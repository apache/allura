import re
from time import sleep

import tg
import pymongo
from pylons import c, g, request
from pymongo.bson import ObjectId

from ming import schema
from ming.orm.base import mapper, session
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, RelationProperty, ForeignIdProperty

from pyforge.lib.helpers import nonce
from pyforge.model import Artifact, Message, File
from pyforge.model import VersionedArtifact, Snapshot

common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')

class Forum(Artifact):
    class __mongometa__:
        name='forum'
    type_s = 'Forum'

    parent_id = FieldProperty(schema.ObjectId, if_missing=None)
    shortname = FieldProperty(str)
    name = FieldProperty(str)
    description = FieldProperty(str, if_missing='')
    num_topics = FieldProperty(int, if_missing=0)
    num_posts = FieldProperty(int, if_missing=0)
    subscriptions = FieldProperty({str:bool})

    threads = RelationProperty('Thread')

    def update_stats(self):
        self.num_topics = Thread.query.find(dict(forum_id=self._id)).count()
        self.num_posts = Post.query.find(dict(forum_id=self._id, status='ok')).count()

    def breadcrumbs(self):
        if self.parent:
            l = self.parent.breadcrumbs()
        else:
            l = []
        return l + [(self.name, self.url())]

    @property
    def email_address(self):
        domain = '.'.join(reversed(self.app.url[1:-1].split('/')))
        return '%s@%s%s' % (self.shortname.replace('/', '.'), domain, common_suffix)

    @property
    def last_post(self):
        q = Post.query.find(dict(
                forum_id=self._id)).sort('timestamp', pymongo.DESCENDING)
        return q.first()

    @property
    def parent(self):
        return Forum.query.get(_id=self.parent_id)

    @property
    def subforums(self):
        return Forum.query.find(dict(parent_id=self._id)).all()
        
    def url(self):
        return self.app.url + self.shortname + '/'
    
    def shorthand_id(self):
        return self.shortname

    def index(self):
        result = Artifact.index(self)
        result.update(type_s=self.type_s,
                      name_s=self.name,
                      text=self.description)
        return result

    def subscription(self):
        return self.subscriptions.get(str(c.user._id))

    def delete(self):
        # Delete the subforums
        for sf in self.subforums:
            sf.delete()
        # Delete all the threads, posts, and artifacts
        Thread.query.remove(dict(forum_id=self._id))
        Post.query.remove(dict(forum_id=self._id))
        for att in Attachment.by_metadata(forum_id=self._id):
            att.delete()
        Artifact.delete(self)

class Thread(Artifact):
    class __mongometa__:
        name='thread'
        indexes = [
            'tags' ]
    type_s = 'Thread'

    _id=FieldProperty(str, if_missing=lambda:nonce(8))
    forum_id = ForeignIdProperty(Forum)
    subject = FieldProperty(str)
    num_replies = FieldProperty(int, if_missing=0)
    num_views = FieldProperty(int, if_missing=0)
    subscriptions = FieldProperty({str:bool})
    tags = FieldProperty([str])
    first_post_id = ForeignIdProperty('Post')

    forum = RelationProperty(Forum)
    posts = RelationProperty('Post')
    first_post = RelationProperty('Post')

    def update_stats(self):
        self.num_replies = Post.query.find(dict(thread_id=self._id, status='ok')).count() - 1

    @property
    def last_post(self):
        q = Post.query.find(dict(
                thread_id=self._id)).sort('timestamp', pymongo.DESCENDING)
        return q.first()

    @property
    def parent(self):
        return Forum.query.get(_id=self.parent_id)

    def find_posts_by_thread(self, offset, limit):
        q = Post.query.find(dict(forum_id=self.forum_id, thread_id=self._id, status='ok'))
        q = q.sort('slug')
        q = q.skip(offset)
        q = q.limit(limit)
        return q.all()

    def find_posts_by_date(self, offset, limit):
        # Sort the posts roughly in threaded order
        q = Post.query.find(dict(forum_id=self.forum_id, thread_id=self._id, status='ok'))
        q = q.sort('timestamp')
        q = q.skip(offset)
        q = q.limit(limit)
        return q.all()

    def top_level_posts(self):
        return Post.query.find(dict(
                thread_id=self._id,
                parent_id=None,
                status='ok'))
        
    def url(self):
        # Can't use self.forum because it might change during the req
        forum = Forum.query.get(_id=self.forum_id)
        return forum.url() + 'thread/' + str(self._id) + '/'
    
    def shorthand_id(self):
        return '%s/%s' % (self.forum.shorthand_id(), self._id)

    def index(self):
        result = Artifact.index(self)
        result.update(type_s=self.type_s,
                      name_s=self.subject,
                      views_i=self.num_views,
                      text=self.subject)
        return result

    def subscription(self):
        return self.subscriptions.get(str(c.user._id))

    def delete(self):
        for p in Post.query.find(dict(thread_id=self._id)):
            p.delete()
        Artifact.delete(self)

    def set_forum(self, new_forum):
        self.forum_id = new_forum._id
        Post.query.update(
            dict(thread_id=self._id),
            {'$set':dict(forum_id=new_forum._id)})

class PostHistory(Snapshot):
    class __mongometa__:
        name='post_history'

    artifact_id = ForeignIdProperty('Post')

    def original(self):
        return Post.query.get(_id=self.artifact_id)
        
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
    forum_id = ForeignIdProperty(Forum)
    subject = FieldProperty(str)
    status = FieldProperty(schema.OneOf('ok', 'pending', 'spam', if_missing='pending'))
    flagged_by = FieldProperty([schema.ObjectId])
    flags = FieldProperty(int, if_missing=0)

    thread = RelationProperty(Thread)
    forum = RelationProperty(Forum)

    @property
    def parent(self):
        return Post.query.get(_id=self.parent_id)

    def url(self):
        if self.thread:
            return self.thread.url() + self.slug + '/'
        else:
            return None
    
    def shorthand_id(self):
        if self.thread:
            return '%s#%s' % (self.thread.shorthand_id(), self.slug)
        else:
            return None

    def index(self):
        result = Message.index(self)
        result.update(type_s=self.type_s,
                      name_s=self.subject)
        return result

    def reply_subject(self):
        if self.subject.lower().startswith('re:'):
            return self.subject
        else:
            return 'Re: ' + self.subject

    def reply_text(self):
        l = [ '%s wrote:' % self.author().display_name ]
        l += [ '> ' + line for line in self.text.split('\n') ]
        return '\n'.join(l)

    @classmethod
    def create_post_threads(cls, posts):
        result = []
        post_index = {}
        for p in sorted(posts, key=lambda p:p.slug):
            pi = dict(post=p, children=[])
            post_index[p._id] = pi
            if p.parent_id in post_index:
                post_index[p.parent_id]['children'].append(pi)
            else:
                result.append(pi)
        return result

    @property
    def attachments(self):
        return Attachment.by_metadata(post_id=self._id)

    def delete(self):
        for att in Attachment.by_metadata(message_id=self._id):
            att.delete()
        Message.delete(self)

    def promote(self, thread_title):
        parent = self.parent
        if parent:
            thd, new_parent = self.forum.new_thread(
                thread_title, 'Discussion moved')
            reply = parent.reply(self.subject, 'Discussion moved')
            reply.text = 'Discussion moved to [here](%s)' % thd.url()
            new_parent.text = 'Discussion moved from [here](%s#post-%s)' % (
                self.thread.url(), reply.slug)
            new_parent.slug = parent.slug
            new_parent.timestamp = parent.timestamp
        else:
            new_parent = None
            thd = Thread(forum_id=self.forum._id,
                         subject=thread_title)
        self.thread_id = thd._id
        if new_parent:
            self.parent_id = new_parent._id
        my_replies = re.compile(r'%s/.*' % self.slug)
        Post.query.update(
            dict(slug=my_replies),
            {'$set':dict(thread_id=thd._id)})
        return thd

    def approve(self):
        self.status = 'ok'
        if self.parent_id:
            parent = Post.query.get(_id=self.parent_id)
            self.slug = parent.slug + '/' + nonce()
            self.forum_id = parent.forum_id
            self.thread_id = parent.thread_id
        else:
            thd = Thread(forum_id=self.forum._id,
                         subject=self.subject)
            self.thread_id = thd._id
            thd.first_post_id = self._id
            g.publish('react', 'Forum.new_thread', dict(thread_id=thd._id))
        self.give_access('moderate', user=self.author())
        self.commit()
        if c.app.config.options.get('PostingPolicy') == 'ApproveOnceModerated':
            c.app.config.grant_permission('unmoderated_post', self.author())
        g.publish('react', 'Forum.new_post', dict(post_id=self._id))
        session(self).flush()
        self.thread.update_stats()
        self.forum.update_stats()

    def spam(self):
        self.status = 'spam'
        g.publish('react', 'spam', dict(artifact_reference=self.dump_ref()),
                  serializer='pickle')

class Attachment(File):
    class __mongometa__:
        name = 'attachment.files'
        indexes = [
            'metadata.filename',
            'metadata.forum_id',
            'metadata.post_id' ]

    # Override the metadata schema here
    metadata=FieldProperty(dict(
            forum_id=schema.ObjectId,
            post_id=str,
            filename=str))

    @property
    def forum(self):
        return Forum.query.get(_id=self.metadata.forum_id)

    @property
    def post(self):
        return Post.query.get(_id=self.metadata.post_id)

    def url(self):
        return self.forum.url() + 'attachment/' + self.filename

MappedClass.compile_all()
