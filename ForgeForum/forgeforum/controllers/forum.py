from tg import expose, validate, redirect, flash
from pylons import g, c, request
from formencode import validators
from pymongo.bson import ObjectId

from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole
from pyforge.lib.search import search

from forgeforum import model

class ForumController(object):

    def __init__(self, forum_id):
        self.forum = model.Forum.query.get(app_config_id=c.app.config._id,
                                           shortname=forum_id)
        self.thread = ThreadsController(self.forum)

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

class ThreadsController(object):

    def __init__(self, forum):
        self.forum = forum

    @expose()
    def new(self, subject, content):
        g.publish('audit', 'Forum.%s' % self.forum.shortname.replace('/', '.'),
                  dict(headers=dict(Subject=subject),
                       payload=content))
        flash('Message posted.  It may take a few seconds before your message '
              'appears.')
        redirect('..')

    def _lookup(self, id, *remainder):
        return ThreadController(id), remainder

class ThreadController(object):

    def __init__(self, thread_id):
        self.thread = model.Thread.query.get(_id=thread_id)

    @expose('forgeforum.templates.thread')
    def index(self, offset=None):
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

    def _lookup(self, id, *remainder):
        return PostController(id), remainder

class PostController(object):

    def __init__(self, post_id):
        self.post = model.Post.query.get(_id=post_id)

    def index(self):
        pass

    @expose()
    def reply(self, subject=None, text=None):
        g.publish('audit', 'Forum.%s' % self.post.forum.shortname.replace('/', '.'),
                  dict(headers={'Subject':subject,
                                'In-Reply-To':self.post.message_id},
                       payload=text))
        flash('Message posted.  It may take a few seconds before your message '
              'appears.')
        redirect(self.post.thread.url())

    def _lookup(self, id, *remainder):
        return PostController(self.post._id + '/' + id), remainder

