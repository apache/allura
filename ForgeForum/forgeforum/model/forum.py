import re
from time import sleep

import tg
import pymongo
from pylons import c, g, request
from pymongo.bson import ObjectId

from ming import schema
from ming.orm.base import mapper
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, RelationProperty, ForeignIdProperty

from pyforge.lib.helpers import nonce
from pyforge.model import Artifact, Message, Filesystem
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
        self.num_posts = Post.query.find(dict(forum_id=self._id)).count()

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

    def new_thread(self, subject, content, message_id=None):
        thd = Thread(forum_id=self._id,
                     subject=subject)
        if message_id is None:
            post = Post(forum_id=self._id,
                        thread_id=thd._id,
                        subject=subject,
                        text=content)
        else:
            post = Post(_id=message_id,
                        forum_id=self._id,
                        thread_id=thd._id,
                        subject=subject,
                        text=content)
        thd.first_post_id = post._id
        post.give_access('moderate', user=post.author())
        post.commit()
        self.num_topics += 1
        self.num_posts += 1
        g.publish('react', 'Forum.new_thread', dict(
                thread_id=thd._id))
        g.publish('react', 'Forum.new_post', dict(
                post_id=post._id))
        return thd, post

    def subscription(self):
        return self.subscriptions.get(str(c.user._id))

    def delete(self):
        # Delete all the threads, posts, and artifacts
        Thread.query.remove(dict(forum_id=self._id))
        Post.query.remove(dict(forum_id=self._id))
        for md in Attachment.find({
                'metadata.forum_id':self._id}):
            Attachment.remove(md['filename'])
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
        self.num_replies = Post.query.find(dict(thread_id=self._id)).count() - 1

    @property
    def last_post(self):
        q = Post.query.find(dict(
                thread_id=self._id)).sort('timestamp', pymongo.DESCENDING)
        return q.first()

    @property
    def parent(self):
        return Forum.query.get(_id=self.parent_id)

    def find_posts_by_thread(self, offset, limit):
        q = Post.query.find(dict(forum_id=self.forum_id, thread_id=self._id))
        q = q.sort('_id')
        q = q.skip(offset)
        q = q.limit(limit)
        return q.all()

    def find_posts_by_date(self, offset, limit):
        # Sort the posts roughly in threaded order
        q = Post.query.find(dict(forum_id=self.forum_id, thread_id=self._id))
        q = q.sort('timestamp')
        q = q.skip(offset)
        q = q.limit(limit)
        return q.all()

    def top_level_posts(self):
        return Post.query.find(dict(
                thread_id=self._id,
                parent_id=None))
        
    def url(self):
        return self.forum.url() + 'thread/' + str(self._id) + '/'
    
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

    thread = RelationProperty(Thread)
    forum = RelationProperty(Forum)
    attachments = RelationProperty('Attachment')

    @property
    def parent(self):
        return Post.query.get(_id=self.parent_id)

    def url(self):
        return self.thread.url() + self.slug + '/'
    
    def shorthand_id(self):
        return '%s#%s' % (self.thread.shorthand_id(), self.slug)

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

    def reply(self, subject, text, message_id=None):
        result = Message.reply(self)
        if message_id:
            result._id = message_id
        result.forum_id = self.forum_id
        result.thread_id = self.thread_id
        result.subject = subject
        result.text = text
        result.give_access('moderate', user=result.author())
        result.commit()
        g.publish('react', 'Forum.new_post', dict(
                post_id=result._id))
        return result

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
        return Attachment.find({
                'metadata.message_id':self._id})

    def attachment_url(self, file_info):
        return self.forum.url() + 'attachment/' + file_info['filename']

    def attachment_filename(self, file_info):
        return file_info['metadata']['filename']

    def delete(self):
        for md in Attachment.find({
                'metadata.message_id':self._id}):
            Attachment.remove(md['filename'])
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

class Attachment(Filesystem):
    class __mongometa__:
        name='attachment'
        indexes = [
            'metadata.forum_id',
            'metadata.message_id',
            'metadata.filename' ]

    @classmethod
    def save(cls, filename, content_type,
             forum_id, message_id, content):
        with cls.open(str(ObjectId()), 'w') as fp:
            fp.content_type = content_type
            fp.metadata = dict(forum_id=forum_id,
                               message_id=message_id,
                               filename=filename)
            fp.write(content)

    @classmethod
    def load(cls, id, offset=0, limit=-1):
        with cls.open(id, 'r') as fp:
            if offset:
                fp.seek(offset)
            return fp.read(limit)
    
MappedClass.compile_all()
