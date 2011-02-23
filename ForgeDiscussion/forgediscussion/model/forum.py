import urllib
import re
from itertools import chain

from ming import schema
from ming.utils import LazyProperty
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, RelationProperty, ForeignIdProperty

from allura import model as M
from allura.lib import utils

config = utils.ConfigProxy(
    common_suffix='forgemail.domain')

class Forum(M.Discussion):
    class __mongometa__:
        name='forum'
    type_s = 'Discussion'

    parent_id = FieldProperty(schema.ObjectId, if_missing=None)
    threads = RelationProperty('ForumThread')
    posts = RelationProperty('ForumPost')
    deleted = FieldProperty(bool, if_missing=False)

    @classmethod
    def attachment_class(cls):
        return ForumAttachment

    @classmethod
    def thread_class(cls):
        return ForumThread

    @LazyProperty
    def threads(self):
        threads = self.thread_class().query.find(dict(discussion_id=self._id)).all()
        sorted_threads = chain(
            (t for t in threads if 'Announcement' in t.flags),
            (t for t in threads if 'Sticky' in t.flags and 'Announcement' not in t.flags),
            (t for t in threads if 'Sticky' not in t.flags and 'Announcement' not in t.flags))
        return list(sorted_threads)

    @property
    def parent(self):
        return Forum.query.get(_id=self.parent_id)

    @property
    def subforums(self):
        return Forum.query.find(dict(parent_id=self._id)).all()

    @property
    def email_address(self):
        domain = '.'.join(reversed(self.app.url[1:-1].split('/'))).replace('_', '-')
        return '%s@%s%s' % (self.shortname.replace('/', '.'), domain, config.common_suffix)

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
        return urllib.quote(self.app.url + self.shortname + '/')

    def delete(self):
        # Delete the subforums
        for sf in self.subforums:
            sf.delete()
        super(Forum, self).delete()

    def get_discussion_thread(self, data=None):
        # If the data is a reply, use the parent's thread
        subject = '[no subject]'
        parent_id = None
        if data is not None:
            parent_id = (data.get('in_reply_to') or [None])[0]
            message_id = data.get('message_id') or ''
            subject = data['headers'].get('Subject', subject)
        if parent_id is not None:
            parent = self.post_class().query.get(_id=parent_id)
            if parent: return parent.thread
        if message_id:
            post = self.post_class().query.get(_id=message_id)
            if post: return post.thread
        # Otherwise it's a new thread
        return self.thread_class()(discussion_id=self._id,subject=subject)

    @property
    def discussion_thread(self):
        return None

    @property
    def icon(self):
        return ForumFile.query.get(forum_id=self._id)

class ForumFile(M.File):
    forum_id=FieldProperty(schema.ObjectId)

class ForumThread(M.Thread):
    class __mongometa__:
        name='forum_thread'
    type_s = 'Thread'

    discussion_id = ForeignIdProperty(Forum)
    first_post_id = ForeignIdProperty('ForumPost')
    flags = FieldProperty([str])

    discussion = RelationProperty(Forum)
    posts = RelationProperty('ForumPost')
    first_post = RelationProperty('ForumPost', via='first_post_id')

    @property
    def status(self):
        return self.first_post.status

    @classmethod
    def attachment_class(cls):
        return ForumAttachment

    def primary(self, primary_class):
        return self

    def post(self, subject, text, message_id=None, parent_id=None, **kw):
        post = super(ForumThread, self).post(text, message_id=message_id, parent_id=parent_id)
        if subject:
            post.subject = subject
        if not self.first_post_id:
            self.first_post_id = post._id
            self.num_replies = 1
        return post

    def set_forum(self, new_forum):
        self.post_class().query.update(
            dict(discussion_id=self.discussion_id, thread_id=self._id),
            {'$set':dict(discussion_id=new_forum._id)})
        self.attachment_class().query.update(
            {'discussion_id':self.discussion_id, 'thread_id':self._id},
            {'$set':dict(discussion_id=new_forum._id)})
        self.discussion_id = new_forum._id

class ForumPostHistory(M.PostHistory):
    class __mongometa__:
        name='post_history'

    artifact_id = ForeignIdProperty('ForumPost')

class ForumPost(M.Post):
    class __mongometa__:
        name='forum_post'
        history_class = ForumPostHistory
    type_s = 'Post'

    subject = FieldProperty(str)
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

    def primary(self, primary_class):
        return self

    def promote(self):
        '''Make the post its own thread head'''
        thd = self.thread_class()(
            discussion_id=self.discussion_id,
            subject=self.subject,
            first_post_id=self._id)
        self.move(thd, None)
        return thd

    def move(self, thread, new_parent_id):
        # Add a placeholder to note the move
        placeholder = self.thread.post(
            subject='Discussion moved',
            text='',
            parent_id=self.parent_id)
        placeholder.slug = self.slug
        placeholder.full_slug = self.full_slug
        placeholder.approve()
        if new_parent_id:
            parent = self.post_class().query.get(_id=new_parent_id)
        else:
            parent = None
        # Set the thread ID on my replies and attachments
        old_slug = self.slug + '/', self.full_slug + '/'
        reply_re = re.compile(self.slug + '/.*')
        self.slug, self.full_slug = self.make_slugs(parent=parent, timestamp=self.timestamp)
        placeholder.text = 'Discussion moved to [here](%s#post-%s)' % (
            thread.url(), self.slug)
        new_slug = self.slug + '/', self.full_slug + '/'
        self.discussion_id=thread.discussion_id
        self.thread_id=thread._id
        self.parent_id=new_parent_id
        self.text = 'Discussion moved from [here](%s#post-%s)\n\n%s' % (
            placeholder.thread.url(), placeholder.slug, self.text)
        reply_tree = self.query.find(dict(slug=reply_re)).all()
        for post in reply_tree:
            post.slug = new_slug[0] + post.slug[len(old_slug[0]):]
            post.full_slug = new_slug[1] + post.slug[len(old_slug[1]):]
            post.discussion_id=self.discussion_id
            post.thread_id=self.thread_id
        for post in [ self ] + reply_tree:
            for att in post.attachments:
                att.discussion_id=self.discussion_id
                att.thread_id=self.thread_id

class ForumAttachment(M.DiscussionAttachment):
    DiscussionClass=Forum
    ThreadClass=ForumThread
    PostClass=ForumPost
    class __mongometa__:
        polymorphic_identity='ForumAttachment'
    attachment_type=FieldProperty(str, if_missing='ForumAttachment')

MappedClass.compile_all()
