import re

import tg
from pylons import g

from ming import schema
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, RelationProperty, ForeignIdProperty

from pyforge import model as M

common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')

class Forum(M.Discussion):
    class __mongometa__:
        name='forum'
    type_s = 'Forum'

    parent_id = FieldProperty(schema.ObjectId, if_missing=None)
    threads = RelationProperty('ForumThread')
    posts = RelationProperty('ForumPost')

    @classmethod
    def attachment_class(cls):
        return ForumAttachment

    @property
    def parent(self):
        return Forum.query.get(_id=self.parent_id)

    @property
    def subforums(self):
        return Forum.query.find(dict(parent_id=self._id)).all()
        
    @property
    def email_address(self):
        domain = '.'.join(reversed(self.app.url[1:-1].split('/')))
        return '%s@%s%s' % (self.shortname.replace('/', '.'), domain, common_suffix)

    def breadcrumbs(self):
        if self.parent:
            l = self.parent.breadcrumbs()
        else:
            l = []
        return l + [(self.name, self.url())]

    def url(self):
        return self.app.url + self.shortname + '/'

    def delete(self):
        # Delete the subforums
        for sf in self.subforums:
            sf.delete()
        super(Forum, self).delete()

    def discussion_thread(self, data=None):
        # If the data is a reply, use the parent's thread
        subject = '[no subject]'
        parent_id = None
        if data is not None:
            parent_id = data['headers'].get('In-Reply-To')
            subject = data['headers'].get('Subject', subject)
        if parent_id is not None:
            parent = self.post_class().query.get(_id=parent_id)
            if parent: return parent.thread
        # Otherwise it's a new thread
        return self.thread_class()(discussion_id=self._id,subject=subject)

class ForumThread(M.Thread):
    class __mongometa__:
        name='forum_thread'
    type_s = 'Thread'

    discussion_id = ForeignIdProperty(Forum)
    first_post_id = ForeignIdProperty('ForumPost')

    discussion = RelationProperty(Forum)
    posts = RelationProperty('ForumPost')
    first_post = RelationProperty('ForumPost')

    @classmethod
    def attachment_class(cls):
        return ForumAttachment

    def post(self, subject, text, message_id=None, parent_id=None, **kw):
        post = super(ForumThread, self).post(text, message_id=message_id, parent_id=parent_id)
        post.subject = subject
        return post

    def set_forum(self, new_forum):
        self.post_class().query.update(
            dict(discussion_id=self.discussion_id, thread_id=self._id),
            {'$set':dict(discussion_id=new_forum._id)})
        self.attachment_class().query.update(
            {'metadata.discussion_id':self.discussion_id,
             'metadata.thread_id':self._id},
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

    def promote(self):
        '''Make the post its own thread head'''
        if not self.parent: return # already its own thread
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
            text='Discussion moved to [here](%s#post-%s)' % (
                thread.url(), self.slug),
            parent_id=self.parent_id)
        placeholder.slug = self.slug
        placeholder.full_slug = self.full_slug
        placeholder.approve()
        if new_parent_id:
            parent = self.post_class().query.get(_id=new_parent_id)
        else:
            parent = None
        # Set the thread ID on my replies and attachments
        reply_re = re.compile(self.slug + '/.*')
        self.slug, self.full_slug = self.make_slugs(parent=parent, timestamp=self.timestamp)
        self.discussion_id=thread.discussion_id
        self.thread_id=thread._id
        self.parent_id=new_parent_id
        self.text = 'Discussion moved from [here](%s#post-%s)\n\n%s' % (
            placeholder.thread.url(), placeholder.slug, self.text)
        reply_tree = self.query.find(dict(slug=reply_re)).all()
        for post in reply_tree:
            post.slug, post.full_slug = self.make_slugs(parent=post.parent, timestamp=post.timestamp)
            post.discussion_id=self.discussion_id,
            post.thread_id=self.thread_id
        for post in [ self ] + reply_tree:
            for att in post.attachments:
                att.discussion_id=self.discussion_id
                att.thread_id=self.thread_id

class ForumAttachment(M.Attachment):
    DiscussionClass=Forum
    ThreadClass=ForumThread
    PostClass=ForumPost
    class __mongometa__:
        name = 'forum_attachment.files'
        indexes = [
            'metadata.filename',
            'metadata.forum_id',
            'metadata.post_id' ]

MappedClass.compile_all()
