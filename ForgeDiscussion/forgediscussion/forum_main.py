#-*- python -*-
import logging
import Image
import pymongo

# Non-stdlib imports
import pkg_resources
from pylons import g, c, request
from tg import expose, redirect, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from pymongo.bson import ObjectId
from ming.orm.base import session
from ming import schema

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib import helpers as h
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole

# Local imports
from forgediscussion import model
from forgediscussion import version
from .controllers import RootController


log = logging.getLogger(__name__)

class ForgeDiscussionApp(Application):
    __version__ = version.__version__
    #installable=False
    permissions = ['configure', 'read', 'unmoderated_post', 'post', 'moderate', 'admin']
    config_options = Application.config_options + [
        ConfigOption('PostingPolicy',
                     schema.OneOf('ApproveOnceModerated', 'ModerateAll'), 'ApproveOnceModerated')
        ]
    PostClass=model.ForumPost
    AttachmentClass=model.ForumAttachment
    searchable=True
    tool_label='Discussion'
    default_mount_label='Discussion'
    default_mount_point='discussion'
    ordinal=7

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = ForumAdminController(self)
        self.default_forum_preferences = dict(
            subscriptions={})

    def has_access(self, user, topic):
        f = model.Forum.query.get(shortname=topic.replace('.', '/'))
        return has_artifact_access('post', f, user=user)()

    @audit('Discussion.msg.#')
    def message_auditor(self, routing_key, data):
        log.info('Auditing data from %s (%s)',
                 routing_key, self.config.options.mount_point)
        log.info('Headers are: %s', data['headers'])
        try:
            shortname = routing_key.split('.', 2)[-1]
            f = model.Forum.query.get(shortname=shortname.replace('.', '/'))
        except:
            log.exception('Error looking up forum: %s', routing_key)
            return
        if f is None:
            log.error("Can't find forum %s (routing key was %s)",
                          shortname, routing_key)
            return
        super(ForgeDiscussionApp, self).message_auditor(
            routing_key, data, f, subject=data['headers'].get('Subject', '[No Subject]'))

    @audit('Discussion.forum_stats.#')
    def forum_stats_auditor(self, routing_key, data):
        try:
            shortname = routing_key.split('.', 2)[-1]
            f = model.Forum.query.get(shortname=shortname.replace('.', '/'))
        except:
            log.exception('Error looking up forum: %s', routing_key)
            return
        if f is None:
            log.error("Can't find forum %s (routing key was %s)",
                          shortname, routing_key)
            return
        f.update_stats()

    @audit('Discussion.thread_stats.#')
    def thread_stats_auditor(self, routing_key, data):
        try:
            thread_id = routing_key.split('.', 2)[-1]
            thread = model.ForumThread.query.find(_id=thread_id)
        except:
            log.exception('Error looking up forum: %s', routing_key)
            return
        if thread is None:
            log.error("Can't find thread %s (routing key was %s)",
                      thread_id, routing_key)
            return
        thread.update_stats()

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

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

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = super(ForgeDiscussionApp, self).admin_menu()
        if has_artifact_access('configure', app=self)():
            links.append(SitemapEntry('Forums', admin_url + 'forums', className='nav_child'))
        return links

    def sidebar_menu(self):
        try:
            l = [SitemapEntry('Home', c.app.url, ui_icon='home')]
            # if we are in a thread, provide placeholder links to use in js
            if '/thread/' in request.url:
                l += [
                    SitemapEntry('Reply to This', '#', ui_icon='comment', className='sidebar_thread_reply'),
                    SitemapEntry('Tag This', '#', ui_icon='tag', className='sidebar_thread_tag'),
                    SitemapEntry('Follow This', 'feed.rss', ui_icon='signal-diag'),
                    SitemapEntry('Mark as Spam', 'flag_as_spam', ui_icon='flag', className='sidebar_thread_spam')
                ]
            else:
                l.append(SitemapEntry('Search', c.app.url+'search', ui_icon='search'))
            if has_artifact_access('admin', app=c.app)():
                l.append(SitemapEntry('Admin', c.project.url()+'admin/'+self.config.options.mount_point, ui_icon='wrench'))
            recent_topics = [ SitemapEntry(h.text.truncate(thread.subject, 72), thread.url(), className='nav_child',
                                small=thread.num_replies)
                   for thread in model.ForumThread.query.find().sort('mod_date', pymongo.DESCENDING).limit(3)
                   if (not thread.discussion.deleted or has_artifact_access('configure', app=c.app)()) ]
            if len(recent_topics):
                l.append(SitemapEntry('Recent Topics'))
                l += recent_topics
            l.append(SitemapEntry('Forum Help'))
            l.append(SitemapEntry('Forum Permissions', c.app.url + 'help', className='nav_child'))
            l.append(SitemapEntry('Markdown Syntax', c.app.url + 'markdown_syntax', className='nav_child'))
            return l
        except: # pragma no cover
            log.exception('sidebar_menu')
            return []
        
    @property
    def templates(self):
         return pkg_resources.resource_filename('forgediscussion', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'
        # Don't call super install here, as that sets up discussion for a tool

        # Setup permissions
        role_developer = ProjectRole.query.get(name='Developer')._id
        role_auth = ProjectRole.query.get(name='*authenticated')._id
        role_anon = ProjectRole.query.get(name='*anonymous')._id
        self.config.acl.update(
            configure=c.project.acl['tool'],
            read=c.project.acl['read'],
            unmoderated_post=[role_auth],
            post=[role_anon],
            moderate=[role_developer],
            admin=c.project.acl['tool'])
        
        self.admin.create_forum(new_forum=dict(
            shortname='general',
            create='on',
            name='General Discussion',
            description='Forum about anything you want to talk about.',
            parent=''))

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        model.Forum.query.remove(dict(app_config_id=self.config._id))
        model.ForumThread.query.remove(dict(app_config_id=self.config._id))
        model.ForumPost.query.remove(dict(app_config_id=self.config._id))
        super(ForgeDiscussionApp, self).uninstall(project)

class ForumAdminController(DefaultAdminController):

    def _check_security(self):
        require(has_artifact_access('admin', app=self.app), 'Admin access required')

    @with_trailing_slash
    def index(self, **kw):
        redirect('forums')

    @expose('forgediscussion.templates.admin_forums')
    def forums(self):
        return dict(app=self.app,
                    allow_config=has_artifact_access('configure', app=self.app)())

    def save_forum_icon(self, forum, icon):                
        if h.supported_by_PIL(icon.type):
            filename = icon.filename
            if icon.type: content_type = icon.type
            else: content_type = 'application/octet-stream'
            image = Image.open(icon.file)
            format = image.format
            image = h.square_image(image)
            image.thumbnail((48, 48), Image.ANTIALIAS)
            if forum.icon:
                model.ForumFile.query.remove({'metadata.forum_id':forum._id})
            with model.ForumFile.create(
                content_type=content_type,
                filename=filename,
                forum_id=forum._id) as fp:
                image.save(fp, format)
        else:
            flash('The icon must be jpg, png, or gif format.')

    def create_forum(self, new_forum):    
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
        if 'icon' in new_forum and new_forum['icon'] is not None and new_forum['icon'] != '':
            self.save_forum_icon(f, new_forum['icon'])
        return f

    @h.vardec
    @expose()
    def update_forums(self, forum=None, new_forum=None, **kw):
        if forum is None: forum = []
        if new_forum.get('create'):
            if '.' in new_forum['shortname'] or '/' in new_forum['shortname']:
                flash('Shortname cannot contain . or /', 'error')
                redirect('.')
            f = self.create_forum(new_forum)
        for f in forum:
            forum = model.Forum.query.get(_id=ObjectId(str(f['id'])))
            if f.get('delete'):
                forum.deleted=True
            elif f.get('undelete'):
                forum.deleted=False
            else:
                forum.name = f['name']
                forum.description = f['description']
                if 'icon' in f and f['icon'] is not None and f['icon'] != '':
                    self.save_forum_icon(forum, f['icon'])
        flash('Forums updated')
        redirect(request.referrer)
