#-*- python -*-
import logging

# Non-stdlib imports
import pkg_resources
from pylons import g, c, request
from tg import expose, redirect, flash
from pymongo.bson import ObjectId
from ming.orm.base import session
from ming import schema

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib.helpers import push_config, vardec
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import User, File
from pyforge.model.artifact import gen_message_id

# Local imports
from forgeforum import model
from forgeforum import version
from .controllers import RootController


log = logging.getLogger(__name__)

class ForgeForumApp(Application):
    __version__ = version.__version__
    permissions = ['configure', 'read', 'unmoderated_post', 'post', 'moderate', 'admin']
    config_options = Application.config_options + [
        ConfigOption('PostingPolicy',
                     schema.OneOf('ApproveOnceModerated', 'ModerateAll'), 'ApproveOnceModerated')
        ]

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = ForumAdminController(self)
        self.default_forum_preferences = dict(
            subscriptions={})

    def has_access(self, user, topic):
        f = model.Forum.query.get(shortname=topic.replace('.', '/'))
        return has_artifact_access('post', f, user=user)()

    @audit('Forum.msg.#')
    def auditor(self, routing_key, data):
        message_id = data.get('message_id', [gen_message_id()])
        in_reply_to = data.get('in_reply_to', [])
        references = data.get('references', [])
        log.info('Auditing data from %s (%s)\n'
                 '\tmessage_id : %s\n'
                 '\tin_reply_to: %s\n'
                 '\treferences : %s',
                 routing_key,
                 self.config.options.mount_point,
                 message_id,
                 in_reply_to,
                 references)
        try:
            shortname = routing_key.split('.', 2)[-1]
            f = model.Forum.query.get(shortname=shortname.replace('.', '/'))
        except:
            log.exception('Error processing data: %s', data)
            return
        if f is None:
            log.info('routing key is %s', routing_key)
            log.exception('Cannot find forum %s', shortname)
            return
        # Handle attachments
        if data.get('filename'):
            log.info('Saving attachment %s', data['filename'])
            model.Attachment.save(data['filename'],
                                  data.get('content_type', 'application/octet-stream'),
                                  data['payload'],
                                  forum_id=f._id,
                                  post_id=message_id[0])
            return
        # Handle duplicates
        original = model.Post.query.get(_id=message_id[0])
        if original:
            log.info('Saving text attachment')
            model.Attachment.save('alternate',
                                  data.get('content_type', 'application/octet-stream'),
                                  data['payload'],
                                  forum_id=f._id,
                                  post_id=message_id[0])
            return
        # Find parent post
        if in_reply_to:
            parent = model.Post.query.get(_id=in_reply_to[0])
        else:
            parent = None
        log.info('In reply to parent: %s', parent)
        subject = data['headers'].get('Subject')
        text = data['payload']
        # Create 'orphan' post for moderation
        post = model.Post(_id=message_id[0],
                    forum_id=f._id,
                    subject=subject,
                    text=text)
        if parent:
            post.parent_id = parent._id
        self._classify_post(f, post)

    def _classify_post(self, forum, post):
        if has_artifact_access('unmoderated_post')():
            post.approve()
        elif has_artifact_access('post')():
            pass
        else:
            post.delete() # poster has no access
        session(post).flush()

    @react('Forum.new_post')
    def notify_subscribers(self, routing_key, data):
        log.info('Got a new post: %s', data['post_id'])
        post = model.Post.query.get(_id=data.get('post_id'))
        thread = post.thread
        forum = thread.forum
        subs = set()
        for un, sub in thread.subscriptions.iteritems():
            if sub: subs.add(un)
        for un, sub in forum.subscriptions.iteritems():
            if sub: subs.add(un)
        msg = {
            'message_id':post._id,
            'destinations':list(subs),
            'from':forum.email_address,
            'subject':'[%s] %s' % (forum.name, post.subject),
            'text':post.text}
        if post.parent:
            msg['in_reply_to'] = [post.parent._id]
        g.publish('audit', 'forgemail.send_email', msg)

    @property
    def sitemap(self):
        try:
            menu_id = self.config.options.mount_point.title()
            with push_config(c, app=self):
                return [
                    SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]
        except: # pragma no cover
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
                   for f in self.top_forums ]
            return l
        except: # pragma no cover
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

    def _check_security(self):
        require(has_artifact_access('admin', app=self.app), 'Admin access required')

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
                forum.delete()
            else:
                forum.name = f['name']
                forum.description = f['description']
        flash('Forums updated')
        redirect('.')
