#-*- python -*-
import logging

# Non-stdlib imports
import pkg_resources
from pylons import g, c, request
from tg import expose, redirect, flash
from pymongo.bson import ObjectId

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib.helpers import push_config, vardec
from pyforge.lib.decorators import audit, react
from pyforge.model import User

# Local imports
from forgeforum import model
from forgeforum import version
from .controllers import RootController

log = logging.getLogger(__name__)

class ForgeForumApp(Application):
    __version__ = version.__version__
    permissions = ['configure', 'read', 'post', 'moderate', 'admin']
    config_options = Application.config_options

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = ForumAdminController(self)
        self.default_forum_preferences = dict(
            subscriptions={})

    def has_access(self, user, topic):
        return user != User.anonymous()

    @audit('Forum.#')
    def auditor(self, routing_key, data):
        log.info('Auditing data from %s (%s)',
                 routing_key, self.config.options.mount_point)
        log.info('Headers are: %s', data['headers'])
        try:
            header, shortname = routing_key.split('.', 1)
            f = model.Forum.query.get(shortname=shortname.replace('.', '/'))
        except:
            log.exception('Error processing data: %s', data)
            return
        # Find ancestor post
        parent = model.Post.query.get(message_id=data['headers'].get('In-Reply-To'))
        subject = data['headers'].get('Subject')
        text = data['payload']
        if parent is None:
            thd, post = f.new_thread(subject, text)
        else:
            post = parent.reply(subject, text)
        post.thread.num_replies = (
            model.Post.query.find(dict(thread_id=post.thread_id)).count())
        log.info('Set num_replies on thread to %s', post.thread.num_replies)
        post.message_id = data['headers'].get('Message-ID', post.message_id)

    @react('Forum.new_post')
    def notify_subscribers(self, routing_key, data):
        post = model.Post.query.get(_id=data.pop('post_id'))
        thread = post.thread
        forum = thread.forum
        subs = set()
        for un, sub in thread.subscriptions.iteritems():
            if sub: subs.add(un)
        for un, sub in forum.subscriptions.iteritems():
            if sub: subs.add(un)
        msg = {
            'message_id':post.message_id,
            'destinations':list(subs),
            'from':forum.email_address,
            'subject':'[%s] %s' % (forum.name, post.subject),
            'text':post.text}
        if post.parent:
            msg['in_reply_to'] = post.parent.message_id
        g.publish('audit', 'forgemail.send_email', msg)

    @react('ForgeForum.#')
    def reactor(self, routing_key, data):
        log.info('Reacting to data from %s (%s)',
                 routing_key, self.config.options.mount_point)

    @property
    def sitemap(self):
        try:
            menu_id = 'ForgeForum (%s)' % self.config.options.mount_point  
            with push_config(c, app=self):
                return [
                    SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]
        except:
            log.exception('sitemap')
            return []

    @property
    def forums(self):
        return model.Forum.query.find(dict(app_config_id=self.config._id)).all()

    @property
    def top_forums(self):
        return self.subforums_of(None)

    def subforums_of(self, parent_id):
        return model.Forum.query.find(dict(
                app_config_id=self.config._id,
                parent_id=parent_id,
                )).all()

    def sidebar_menu(self):
        try:
            l =  [
                SitemapEntry('Home', '.'),      
                SitemapEntry('Search', 'search'),      
                ]
            l += [ SitemapEntry(f.name, f.url())
                   for f in self.forums ]
            return l
        except:
            log.exception('sidebar_menu')
            return []
        
    @property
    def templates(self):
         return pkg_resources.resource_filename('forgeforum', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'

        self.uninstall(project)
        # Give the installing user all the permissions
        pr = c.user.project_role()
        for perm in self.permissions:
              self.config.acl[perm] = [ pr._id ]

    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        model.Forum.query.remove(dict(app_config_id=self.config._id))
        model.Thread.query.remove(dict(app_config_id=self.config._id))
        model.Post.query.remove(dict(app_config_id=self.config._id))

class ForumAdminController(DefaultAdminController):

    @expose('forgeforum.templates.admin')
    def index(self):
        return dict(app=self.app)

    @vardec
    @expose()
    def update_forums(self, forum=None, new_forum=None, **kw):
        if forum is None: forum = []
        if new_forum.get('create'):
            if '.' in new_forum['shortname'] or '/' in new_forum['shortname']:
                flash('Shortname cannot contain . or /', 'error')
                redirect('.')
            if new_forum['parent']:
                parent_id = ObjectId(str(new_forum['parent']))
                shortname = (model.Forum.query.get(_id=parent_id).shortname + '/'
                             + new_forum['shortname'])
            else:
                parent_id=None
                shortname = new_forum['shortname']
            f = model.Forum(app_config_id=self.app.config._id,
                            parent_id=parent_id,
                            name=new_forum['name'],
                            shortname=shortname,
                            description=new_forum['description'])
        for f in forum:
            forum = model.Forum.query.get(_id=ObjectId(str(f['id'])))
            if f.get('delete'):
                for t in forum.threads:
                    model.Post.query.remove(dict(app_config_id=self.app.config._id,
                                                 thread_id=t._id))
                    t.delete()
                forum.delete()
                continue
            forum.name = f['name']
            forum.description = f['description']
        redirect('.')
