#-*- python -*-
import logging
import urllib
from itertools import islice

# Non-stdlib imports
import pymongo
from pylons import g, c, request
from tg import expose, redirect, flash, url, validate
from tg.decorators import with_trailing_slash
from bson import ObjectId
from ming import schema

# Pyforge-specific imports
from allura import model as M
from allura.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from allura.lib import helpers as h
from allura.lib.decorators import require_post
from allura.lib.security import require, has_artifact_access

# Local imports
from forgediscussion import model as DM
from forgediscussion import version
from .controllers import RootController

from widgets.admin import OptionsAdmin, AddForum


log = logging.getLogger(__name__)

class W:
    options_admin = OptionsAdmin()
    add_forum = AddForum()

class ForgeDiscussionApp(Application):
    __version__ = version.__version__
    #installable=False
    permissions = ['configure', 'read', 'unmoderated_post', 'post', 'moderate', 'admin']
    config_options = Application.config_options + [
        ConfigOption('PostingPolicy',
                     schema.OneOf('ApproveOnceModerated', 'ModerateAll'), 'ApproveOnceModerated')
        ]
    PostClass=DM.ForumPost
    AttachmentClass=DM.ForumAttachment
    searchable=True
    tool_label='Discussion'
    default_mount_label='Discussion'
    default_mount_point='discussion'
    ordinal=7
    icons={
        24:'allura/images/forums_24.png',
        32:'allura/images/forums_32.png',
        48:'allura/images/forums_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = ForumAdminController(self)
        self.default_forum_preferences = dict(
            subscriptions={})

    def has_access(self, user, topic):
        f = DM.Forum.query.get(shortname=topic.replace('.', '/'),
                               app_config_id=self.config._id)
        return has_artifact_access('post', f, user=user)()

    def handle_message(self, topic, message):
        log.info('Message from %s (%s)',
                 topic, self.config.options.mount_point)
        log.info('Headers are: %s', message['headers'])
        shortname=urllib.unquote_plus(topic.replace('.', '/'))
        forum = DM.Forum.query.get(
            shortname=shortname, app_config_id=self.config._id)
        if forum is None:
            log.error("Error looking up forum: %r", shortname)
            return
        self.handle_artifact_message(forum, message)

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    @property
    def forums(self):
        return DM.Forum.query.find(dict(app_config_id=self.config._id)).all()

    @property
    def top_forums(self):
        return self.subforums_of(None)

    def subforums_of(self, parent_id):
        return DM.Forum.query.find(dict(
                app_config_id=self.config._id,
                parent_id=parent_id,
                )).all()

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = super(ForgeDiscussionApp, self).admin_menu()
        if has_artifact_access('configure', app=self)():
            links.append(SitemapEntry('Forums', admin_url + 'forums'))
        if self.permissions and has_artifact_access('configure', app=self)():
            links.append(SitemapEntry('Permissions', admin_url + 'permissions', className='nav_child'))
        return links

    def sidebar_menu(self):
        try:
            l = []
            moderate_link = None
            forum_links = []
            forums = DM.Forum.query.find(dict(
                            app_config_id=c.app.config._id,
                            parent_id=None)).all()
            if forums:
                for f in forums:
                    if f.url() in request.url and h.has_artifact_access('moderate', f)():
                        moderate_link = SitemapEntry('Moderate', "%smoderate/" % f.url(), ui_icon=g.icons['pencil'],
                        small = DM.ForumPost.query.find({'discussion_id':f._id, 'status':{'$ne': 'ok'}}).count())
                    forum_links.append(SitemapEntry(f.name, f.url(), className='nav_child'))
            if has_artifact_access('post', app=c.app)():
                l.append(SitemapEntry('Create Topic', c.app.url + 'create_topic', ui_icon=g.icons['plus']))
            if has_artifact_access('configure', app=c.app)():
                l.append(SitemapEntry('Add Forum', url(c.app.url,dict(new_forum=True)), ui_icon=g.icons['conversation']))
                l.append(SitemapEntry('Admin Forums', c.project.url()+'admin/'+self.config.options.mount_point+'/forums', ui_icon=g.icons['pencil']))
            if moderate_link:
                l.append(moderate_link)
            # if we are in a thread, provide placeholder links to use in js
            if '/thread/' in request.url:
                l.append(SitemapEntry(
                        'Mark as Spam', 'flag_as_spam',
                        ui_icon=g.icons['flag'], className='sidebar_thread_spam'))
            # Get most recently-posted-to-threads across all discussions in this app
            recent_threads = (
                thread for thread in (
                    DM.ForumThread.query.find(
                        dict(app_config_id=self.config._id))
                    .sort([
                            ('last_post_date', pymongo.DESCENDING),
                            ('mod_date', pymongo.DESCENDING)])
                    ))
            recent_threads = (
                t for t in recent_threads 
                if (has_artifact_access('configure') or not thread.discussion.deleted) )
            recent_threads = ( t for t in recent_threads if t.status == 'ok' )
            # Limit to 3 threads
            recent_threads = list(islice(recent_threads, 3))
            # Add to sitemap
            if recent_threads:
                l.append(SitemapEntry('Recent Topics'))
                l += [
                    SitemapEntry(
                        h.text.truncate(thread.subject, 72), thread.url(),
                        className='nav_child', small=thread.num_replies)
                    for thread in recent_threads ]
            if forum_links:
                l.append(SitemapEntry('Forums'))
                l = l + forum_links
            l.append(SitemapEntry('Help'))
            l.append(SitemapEntry('Forum Help', c.app.url + 'help', className='nav_child'))
            l.append(SitemapEntry('Markdown Syntax', c.app.url + 'markdown_syntax', className='nav_child'))
            return l
        except: # pragma no cover
            log.exception('sidebar_menu')
            return []

    def install(self, project):
        'Set up any default permissions and roles here'
        # Don't call super install here, as that sets up discussion for a tool

        # Setup permissions
        role_developer = M.ProjectRole.by_name('Developer')._id
        role_auth = M.ProjectRole.by_name('*authenticated')._id
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        self.config.acl.update(
            configure=c.project.roleids_with_permission('tool'),
            read=c.project.roleids_with_permission('read'),
            unmoderated_post=[role_auth],
            post=[role_anon],
            moderate=[role_developer],
            admin=c.project.roleids_with_permission('tool'))

        self.admin.create_forum(new_forum=dict(
            shortname='general',
            create='on',
            name='General Discussion',
            description='Forum about anything you want to talk about.',
            parent=''))

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        DM.Forum.query.remove(dict(app_config_id=self.config._id))
        DM.ForumThread.query.remove(dict(app_config_id=self.config._id))
        DM.ForumPost.query.remove(dict(app_config_id=self.config._id))
        super(ForgeDiscussionApp, self).uninstall(project)

class ForumAdminController(DefaultAdminController):

    def _check_security(self):
        require(has_artifact_access('admin', app=self.app), 'Admin access required')

    @with_trailing_slash
    def index(self, **kw):
        redirect('forums')

    @expose('jinja:forgediscussion:templates/discussionforums/admin_options.html')
    def options(self):
        c.options_admin = W.options_admin
        return dict(app=self.app,
                    form_value=dict(
                        PostingPolicy=self.app.config.options.get('PostingPolicy')
                    ))

    @expose('jinja:forgediscussion:templates/discussionforums/admin_forums.html')
    def forums(self, add_forum=None, **kw):
        c.add_forum = W.add_forum
        return dict(app=self.app,
                    allow_config=has_artifact_access('configure', app=self.app)())

    def save_forum_icon(self, forum, icon):
        if forum.icon: forum.icon.delete()
        DM.ForumFile.save_image(
            icon.filename, icon.file, content_type=icon.type,
            square=True, thumbnail_size=(48, 48),
            thumbnail_meta=dict(forum_id=forum._id))

    def create_forum(self, new_forum):
        if 'parent' in new_forum and new_forum['parent']:
            parent_id = ObjectId(str(new_forum['parent']))
            shortname = (DM.Forum.query.get(_id=parent_id).shortname + '/'
                         + new_forum['shortname'])
        else:
            parent_id=None
            shortname = new_forum['shortname']
        description = ''
        if 'description' in new_forum:
            description=new_forum['description']
        f = DM.Forum(app_config_id=self.app.config._id,
                        parent_id=parent_id,
                        name=h.really_unicode(new_forum['name']).encode('utf-8'),
                        shortname=h.really_unicode(shortname).encode('utf-8'),
                        description=h.really_unicode(description).encode('utf-8'))
        if 'icon' in new_forum and new_forum['icon'] is not None and new_forum['icon'] != '':
            self.save_forum_icon(f, new_forum['icon'])
        return f

    @h.vardec
    @expose()
    @require_post()
    def update_forums(self, forum=None, **kw):
        if forum is None: forum = []
        for f in forum:
            forum = DM.Forum.query.get(_id=ObjectId(str(f['id'])))
            if f.get('delete'):
                forum.deleted=True
            elif f.get('undelete'):
                forum.deleted=False
            else:
                if '.' in f['shortname'] or '/' in f['shortname'] or ' ' in f['shortname']:
                    flash('Shortname cannot contain space . or /', 'error')
                    redirect('.')
                forum.name = f['name']
                forum.shortname = f['shortname']
                forum.description = f['description']
                if 'icon' in f and f['icon'] is not None and f['icon'] != '':
                    self.save_forum_icon(forum, f['icon'])
        flash('Forums updated')
        redirect(request.referrer)

    @h.vardec
    @expose()
    @require_post()
    @validate(form=W.add_forum, error_handler=forums)
    def add_forum(self, add_forum=None, **kw):
        f = self.create_forum(add_forum)
        redirect(f.url())
