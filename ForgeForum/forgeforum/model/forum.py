from time import sleep

import tg
import pymongo
from pylons import c, g
from pymongo.bson import ObjectId

from ming import schema
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, RelationProperty, ForeignIdProperty

from pyforge.lib.helpers import nonce
from pyforge.model import Artifact, Message

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

    def breadcrumbs(self):
        if self.parent:
            l = self.parent.breadcrumbs()
        else:
            l = []
        return l + [(self.name, self.url())]

    @property
    def email_address(self):
        if self.parent:
            addr = self.parent.email_address()
            u, d = addr.split('@')
            return '%s.%s@%s' % (u, self.shortname, d)
        domain = '.'.join(reversed(self.app.script_name[1:-1].split('/')))
        return '%s@%s%s' % (self.shortname, domain, common_suffix)

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
        if self.parent:
            return self.parent.url() + self.shortname + '/'
        else:
            return self.app.script_name + self.shortname + '/'
    
    def shorthand_id(self):
        return '%s/%s' % (self.type_s, self._id.url_encode())

    def index(self):
        result = Artifact.index(self)
        result.update(type_s=self.type_s,
                      name_s=self.name,
                      text=self.description)
        return result

    def new_thread(self, subject, content):
        thd = Thread(forum_id=self._id,
                     subject=subject)
        post = Post(forum_id=self._id,
                    thread_id=thd._id,
                    subject=subject,
                    text=content)
        self.num_topics += 1
        self.num_posts += 1
        g.publish('react', 'ForgeForum.new_thread', dict(
                thread_id=thd._id))
        g.publish('react', 'ForgeForum.new_post', dict(
                post_id=post._id))
        return thd

    def subscription(self):
        return self.subscriptions.get(str(c.user._id))

class Thread(Artifact):
    class __mongometa__:
        name='thread'
    type_s = 'Thread'

    _id=FieldProperty(str, if_missing=lambda:nonce(8))
    forum_id = ForeignIdProperty(Forum)
    subject = FieldProperty(str)
    num_replies = FieldProperty(int, if_missing=0)
    num_views = FieldProperty(int, if_missing=0)
    subscriptions = FieldProperty({str:bool})

    forum = RelationProperty(Forum)
    posts = RelationProperty('Post')

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
        return '%s/%s' % (self.type_s, self._id)

    def index(self):
        result = Artifact.index(self)
        result.update(type_s=self.type_s,
                      name_s=self.subject,
                      views_i=self.num_views,
                      text=self.subject)
        return result

    def subscription(self):
        return self.subscriptions.get(str(c.user._id))

class Post(Message):
    class __mongometa__:
        name='post'
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
        return self.thread.url() + self._id + '/'
    
    def shorthand_id(self):
        return '%s/%s' % (self.type_s, self._id)

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

    def reply(self, subject, text):
        result = Message.reply(self)
        result.forum_id = self.forum_id
        result.thread_id = self.thread_id
        result.subject = subject
        result.text = text
        g.publish('react', 'ForgeForum.new_post', dict(
                post_id=result._id))
        return result

    @classmethod
    def create_post_threads(cls, posts):
        result = []
        post_index = {}
        for p in posts:
            pi = dict(post=p, children=[])
            post_index[p._id] = pi
            if p.parent_id in post_index:
                post_index[p.parent_id]['children'].append(pi)
            else:
                result.append(pi)
        return result

class Attachment(Artifact):
    class __mongometa__:
        name='post'
    type_s = 'Post'

    post_id = ForeignIdProperty(Post)
    filename = FieldProperty(str)
    mimetype = FieldProperty(str)
    content = FieldProperty(schema.Binary)
    
MappedClass.compile_all()
