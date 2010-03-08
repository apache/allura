import shlex
import logging
from mimetypes import guess_type
from urllib import unquote

from tg import expose, validate, redirect, flash
from tg import request, response
from pylons import g, c
from ming.base import Object
from webob import exc

from pyforge.lib import helpers as h
from pyforge.lib.security import require, has_artifact_access
from pyforge.controllers import DiscussionController, ThreadController, PostController
from pyforge.lib.widgets import discuss as DW

from forgeforum import model
from forgeforum import widgets as FW

log = logging.getLogger(__name__)

class pass_validator(object):
    def validate(self, v, s):
        return v
pass_validator=pass_validator()

class ModelConfig(object):
    Discussion=model.Forum
    Thread=model.ForumThread
    Post=model.ForumPost
    Attachment=model.ForumAttachment

class WidgetConfig(object):
    # Forms
    subscription_form = DW.SubscriptionForm()
    edit_post = DW.EditPost(show_subject=True)
    moderate_post = FW.ModeratePost()
    moderate_thread = FW.ModerateThread()
    flag_post = DW.FlagPost()
    post_filter = DW.PostFilter()
    moderate_posts=DW.ModeratePosts()
    # Other widgets
    discussion = FW.Forum()
    thread = FW.Thread()
    post = FW.Post()
    thread_header = FW.ThreadHeader()

class ForumController(DiscussionController):
    M=ModelConfig
    W=WidgetConfig

    def _check_security(self):
        require(has_artifact_access('read', self.discussion))

    def __init__(self, forum_id):
        self.ThreadController = ForumThreadController
        self.PostController = ForumPostController
        self.discussion = model.Forum.query.get(
            app_config_id=c.app.config._id,
            shortname=forum_id)
        super(ForumController, self).__init__()

    def _lookup(self, id, *remainder):
        return ForumController(self.discussion.shortname + '/' + id), remainder

    @h.vardec
    @expose()
    @validate(W.edit_post)
    def post(self, subject=None, text=None, **kw):
        require(has_artifact_access('post', self.discussion))
        thd = self.discussion.discussion_thread(dict(
                headers=dict(Subject=subject)))
        post = thd.post(subject, text)
        redirect(thd.url())

class ForumThreadController(ThreadController):

    @h.vardec
    @expose()
    @validate(pass_validator, error_handler=ThreadController.index)
    def moderate(self, **kw):
        require(has_artifact_access('moderate', self.thread))
        args = self.W.moderate_thread.validate(kw, None)
        g.publish('audit', 'Forum.forum_stats.%s' % self.thread.discussion.shortname.replace('/', '.'))
        if args.pop('move', None):
            forum = args.pop('forum')
            g.publish('audit', 'Forum.forum_stats.%s' % forum.shortname.replace('/', '.'))
            self.thread.set_forum(forum)
            redirect(self.thread.url())
        elif args.pop('delete', None):
            url = self.thread.discussion.url()
            self.thread.delete()
            redirect(url)

class ForumPostController(PostController):

    @expose()
    @validate(pass_validator, error_handler=PostController.index)
    def moderate(self, **kw):
        require(has_artifact_access('moderate', self.post.thread))
        args = self.W.moderate_post.validate(kw, None)
        g.publish('audit', 'Forum.thread_stats.%s' % self.post.thread._id)
        g.publish('audit', 'Forum.forum_stats.%s' % self.post.discussion.shortname.replace('/', '.'))
        if args.pop('promote', None):
            self.post.subject = args['subject']
            new_thread = self.post.promote()
            g.publish('audit', 'Forum.thread_stats.%s' % new_thread._id)
            redirect(request.referer)
        super(ForumPostController, self).moderate(**kw)

class OldForumController(object):

    def _check_security(self):
        require(has_artifact_access('read', self.forum))

    def __init__(self, forum_id):
        self.forum = model.Forum.query.get(app_config_id=c.app.config._id,
                                           shortname=forum_id)
        self.thread = ThreadsController(self.forum)
        self.tag = TagsController(self.forum)
        self.attachment = AttachmentsController(self.forum)
        self.moderate = ModerationController(self.forum)

    @expose('forgeforum.templates.forum')
    def index(self):
        threads = self.forum.threads
        return dict(forum=self.forum,
                    threads=threads)
                  
    def _lookup(self, id, *remainder):
        return ForumController(self.forum.shortname + '/' + id), remainder

class TagsController(object):

    def __init__(self, forum):
        self.forum = forum

    def _lookup(self, tag, *remainder):
        tag = unquote(tag).lower()
        return TagController(self.forum, [tag]), remainder

class TagController(object):

    def __init__(self, forum, tags):
        self.forum = forum
        self.tags = tags

    @expose('forgeforum.templates.tag_forum')
    def index(self, tag=None):
        if tag: redirect('%s/' % tag)
        threads = model.Thread.query.find(dict(
                forum_id=self.forum._id,
                tags={'$all':self.tags})).all()
        return dict(forum=self.forum,
                    tags=self.tags,
                    threads=threads)

    def _lookup(self, tag, *remainder):
        tag = unquote(tag).lower()
        return TagController(self.forum, self.tags + [tag]), remainder

class ThreadsController(object):

    def __init__(self, forum):
        self.forum = forum

    @expose()
    def new(self, subject, content):
        require(has_artifact_access('post', self.forum))
        g.publish('audit', 'Forum.msg.%s' % self.forum.shortname.replace('/', '.'),
                  dict(headers=dict(Subject=subject),
                       payload=content))
        flash('Message posted.  It may take a few seconds before your message '
              'appears.')
        redirect('..')

    def _lookup(self, id, *remainder):
        return ThreadController(id), remainder

class ThreadController(object):

    def _check_security(self):
        require(has_artifact_access('read', self.thread))

    def __init__(self, thread_id):
        self.thread = model.Thread.query.get(_id=thread_id)
        self.forum = self.thread.forum

    def _lookup(self, id, *remainder):
        return PostController(self.thread, id), remainder

    @expose('forgeforum.templates.thread')
    def index(self, offset=None):
        if not self.thread.last_post:
            self.thread.delete()
            self.forum.update_stats()
            redirect(self.forum.url())
        pagesize = 15
        style = 'threaded'
        if offset is None: offset = 0
        offset = int(offset)
        if style=="threaded":
            posts = self.thread.find_posts_by_thread(
                offset=offset, limit=pagesize)
            post_threads = model.Post.create_post_threads(posts)
        else: # pragma no cover
            posts = self.thread.find_posts_by_date(
                offset=offset, limit=15)
            post_threads=[]
        self.thread.num_views += 1
        return dict(forum=self.thread.forum,
                    thread=self.thread,
                    post_threads=post_threads,
                    posts=posts,
                    style=style,
                    offset=offset,
                    total=self.thread.num_replies,
                    pagesize=pagesize)

    @expose()
    def moderate(self, forum=None, delete=None):
        require(has_artifact_access('moderate', self.thread))
        if delete:
            url = self.thread.forum.url()
            self.thread.delete()
            redirect(url)
        new_forum = model.Forum.query.get(
            app_config_id=c.app.config._id,
            shortname=forum)
        if not new_forum:
            flash('Forum "%s" not found' % forum, 'error')
            redirect('.')
        self.thread.set_forum(new_forum)
        redirect(self.thread.url())

    @h.vardec
    @expose()
    def update_tags(self, tag=None, new_tag=None, **kw):
        require(has_artifact_access('moderate', self.thread.first_post))
        if tag is None: tag = []
        try:
            asciiname = str(new_tag['name'])
        except UnicodeDecodeError: # pragma no cover
            asciiname = new_tag['name'].encode('utf-8')
        new_tags = [
            t.lower() 
            for t in shlex.split(asciiname, posix=True) ]
        for obj in tag:
            if obj.get('delete'): continue
            new_tags.append(obj['name'])
        self.thread.tags = new_tags
        redirect('.')

class PostController(object):

    def _check_security(self):
        require(has_artifact_access('read', self.post))

    def __init__(self, thread, slug):
        self.thread = thread
        self.post = model.Post.query.get(thread_id=thread._id,
                                         slug=slug)

    @expose('forgeforum.templates.post')
    def index(self, subject=None, text=None, version=None, **kw):
        if request.method == 'POST':
            require(has_artifact_access('moderate', self.post))
            self.post.subject = subject
            self.post.text = text
            self.post.commit()
            redirect(request.referer)
        elif request.method=='GET':
            if version is not None:
                HC = self.post.__mongometa__.history_class
                ss = HC.query.find({'artifact_id':self.post._id, 'version':int(version)}).first()
                if not ss: raise exc.HTTPNotFound
                post = Object(
                    ss.data,
                    acl=self.post.acl,
                    author=self.post.author,
                    url=self.post.url,
                    thread=self.post.thread,
                    reply_subject=self.post.reply_subject,
                    reply_text=self.post.reply_text,
                    attachments=self.post.attachments,
                    )
            else:
                post=self.post
            return dict(forum=self.post.forum,
                        post=post)

    @expose()
    def moderate(self, subject=None, delete=None, spam=None):
        require(has_artifact_access('moderate', self.post.thread))
        if delete:
            self.post.delete()
            self.thread.update_stats()
            redirect(self.thread.url())
        elif spam:
            self.post.status = 'spam'
            self.thread.update_stats()
            redirect(self.thread.url())
        else:
            thd = self.post.promote(subject)
        redirect(thd.url())

    @expose()
    def flag(self):
        if c.user._id not in self.post.flagged_by:
            self.post.flagged_by.append(c.user._id)
            self.post.flags += 1
        redirect(request.referer)

    @expose()
    def reply(self, subject=None, text=None):
        require(has_artifact_access('post', self.thread))
        g.publish('audit',
                  'Forum.msg.%s' % self.post.forum.shortname.replace('/', '.'),
                  dict(headers={'Subject':subject},
                       in_reply_to=[self.post._id],
                       payload=text))
        flash('Message posted.  It may take a few seconds before your message '
              'appears.')
        redirect(self.post.thread.url())

    @expose()
    def attach(self, file_info=None):
        require(has_artifact_access('moderate', self.post))
        filename = file_info.filename
        content_type = guess_type(filename)
        if content_type[0]: content_type = content_type[0]
        else: content_type = 'application/octet-stream'
        with model.Attachment.create(
            content_type=content_type,
            filename=filename,
            forum_id=self.post.forum._id,
            post_id=self.post._id) as fp:
            while True:
                s = file_info.file.read()
                if not s: break
                fp.write(s)
        redirect(self.thread.url() + '#post-' + self.post.slug)

    def _lookup(self, id, *remainder):
        return PostController(self.thread, self.post.slug + '/' + id), remainder

class AttachmentsController(object):

    def __init__(self, forum):
        self.forum = forum
        self.prefix_len = len(self.forum.url()+'attachment/')

    def _lookup(self, filename, *args):
        return AttachmentController(filename), args

class AttachmentController(object):

    def _check_security(self):
        require(has_artifact_access('read', self.post))

    def __init__(self, filename):
        self.filename = filename
        self.attachment = model.Attachment.query.get(filename=filename)
        self.post = self.attachment.post

    @expose() 
    def index(self, delete=False, embed=False):
        if request.method == 'POST':
            require(has_artifact_access('moderate', self.post))
            if delete: self.attachment.delete()
            redirect(request.referer)
        with self.attachment.open() as fp:
            filename = fp.metadata['filename']
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type
            if not embed:
                response.headers.add('Content-Disposition', 
                                     'attachment;filename=%s' % filename)
            return fp.read()
        
    
class ModerationController(object):

    def _check_security(self):
        require(has_artifact_access('moderate', self.forum))

    def __init__(self, forum):
        self.forum = forum

    @expose('forgeforum.templates.moderate')
    def index(self, offset=0, limit=50,
              status='-', flag=None):
        query = dict(
            forum_id=self.forum._id)
        if status != '-':
            query['status'] = status
        if flag:
            query['flags'] = {'$gte': int(flag) }
        print query
        q = model.Post.query.find(query)
        count = q.count()
        offset = int(offset)
        limit = int(limit)
        q = q.skip(offset)
        q = q.limit(limit)
        pgnum = (offset // limit) + 1
        pages = (count // limit) + 1
        return dict(forum=self.forum,
                    posts=q, offset=offset, limit=limit,
                    status=status, flag=flag,
                    pgnum=pgnum, pages=pages)

    @expose()
    @h.vardec
    def moderate(self, post=None,
                 approve=None,
                 spam=None,
                 delete=None,
                 **kw):
        for args in post:
            if not args.get('checked', False): continue
            post = model.Post.query.get(slug=args['slug'])
            if approve:
                if post.status != 'ok': post.approve()
            elif spam:
                if post.status != 'spam': post.spam()
            elif delete:
                post.delete()
        redirect(request.referer)

