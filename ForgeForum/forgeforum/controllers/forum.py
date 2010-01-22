import shlex
import logging
from mimetypes import guess_type
from urllib import unquote

from tg import expose, validate, redirect, flash
from tg import request, response
from pylons import g, c
from formencode import validators
from pymongo.bson import ObjectId
from ming.base import Object
from webob import exc

from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole
from pyforge.lib.search import search
from pyforge.lib.helpers import vardec

from forgeforum import model

log = logging.getLogger(__name__)

class ForumController(object):

    def _check_security(self):
        require(has_artifact_access('read', self.forum))

    def __init__(self, forum_id):
        self.forum = model.Forum.query.get(app_config_id=c.app.config._id,
                                           shortname=forum_id)
        self.thread = ThreadsController(self.forum)
        self.tag = TagsController(self.forum)
        self.attachment = AttachmentsController(self.forum)

    @expose('forgeforum.templates.forum')
    def index(self):
        threads = self.forum.threads
        return dict(forum=self.forum,
                    threads=threads)
                  
    @expose('forgeforum.templates.search')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None):
        'local plugin search'
        results = []
        count=0
        if not q:
            q = ''
        else:
            search_query = '''%s
            AND is_history_b:%s
            AND mount_point_s:%s''' % (
                q, history, c.app.config.options.mount_point)
            results = search(search_query)
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

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
        g.publish('audit', 'Forum.%s' % self.forum.shortname.replace('/', '.'),
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
        else:
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

    @vardec
    @expose()
    def update_tags(self, tag=None, new_tag=None, **kw):
        require(has_artifact_access('moderate', self.thread.first_post))
        try:
            asciiname = str(new_tag['name'])
        except UnicodeDecodeError:
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
    def moderate(self, subject=None, delete=None):
        require(has_artifact_access('moderate', self.post.thread))
        if delete:
            self.post.delete()
            self.thread.update_stats()
        else:
            thd = self.post.promote(subject)
        redirect(thd.url())

    @expose()
    def reply(self, subject=None, text=None):
        require(has_artifact_access('post', self.thread))
        g.publish('audit',
                  'Forum.%s' % self.post.forum.shortname.replace('/', '.'),
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
        if content_type: content_type = content_type[0]
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
        return self.filename
        
    
