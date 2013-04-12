#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import logging
from urllib import basejoin
from cStringIO import StringIO

from tg import expose, redirect, flash
from tg.decorators import without_trailing_slash
from pylons import request, app_globals as g, tmpl_context as c
from paste.deploy.converters import asbool, asint
from bson import ObjectId

from ming.orm import session, state
from ming.utils import LazyProperty

from allura.lib.helpers import push_config, vardec
from allura.lib.security import require, has_access, require_access
from allura import model
from allura.controllers import BaseController
from allura.lib.decorators import require_post, event_handler
from allura.lib.utils import permanent_redirect

log = logging.getLogger(__name__)

class ConfigOption(object):

    def __init__(self, name, ming_type, default, label=None):
        self.name, self.ming_type, self._default, self.label = (
            name, ming_type, default, label or name)

    @property
    def default(self):
        if callable(self._default):
            return self._default()
        return self._default

class SitemapEntry(object):

    def __init__(self, label, url=None, children=None, className=None,
            ui_icon=None, small=None, tool_name=None):
        self.label = label
        self.className = className
        if url is not None:
            url = url.encode('utf-8')
        self.url = url
        self.small = small
        self.ui_icon = ui_icon
        if children is None:
            children = []
        self.children = children
        self.tool_name = tool_name
        self.matching_urls = []

    def __getitem__(self, x):
        """
        Automatically expand the list of sitemap child entries with the given items.  Example:
            SitemapEntry('HelloForge')[
                SitemapEntry('foo')[
                    SitemapEntry('Pages')[pages]
                ]
            ]

        TODO: deprecate this; use a more clear method of building a tree
        """
        if isinstance(x, (list, tuple)):
            self.children.extend(list(x))
        else:
            self.children.append(x)
        return self

    def __repr__(self):
        l = ['<SitemapEntry ']
        l.append('    label=%r' % self.label)
        l.append('    url=%r' % self.url)
        l.append('    children=%s' % repr(self.children).replace('\n', '\n    '))
        l.append('>')
        return '\n'.join(l)

    def bind_app(self, app):
        lbl = self.label
        url = self.url
        if callable(lbl):
            lbl = lbl(app)
        if url is not None:
            url = basejoin(app.url, url)
        return SitemapEntry(lbl, url, [
                ch.bind_app(app) for ch in self.children], className=self.className)

    def extend(self, sitemap):
        child_index = dict(
            (ch.label, ch) for ch in self.children)
        for e in sitemap:
            lbl = e.label
            match = child_index.get(e.label)
            if match and match.url == e.url:
                match.extend(e.children)
            else:
                self.children.append(e)
                child_index[lbl] = e

    def matches_url(self, request):
        """Return true if this SitemapEntry 'matches' the url of `request`."""
        return self.url in request.upath_info or any([
            url in request.upath_info for url in self.matching_urls])

class Application(object):
    """
    The base Allura pluggable application

    After extending this, expose the app by adding an entry point in your setup.py:

        [allura]
        myapp = foo.bar.baz:MyAppClass

    :var status: the status level of this app.  'production' apps are available to all projects
    :var bool searchable: toggle if the search box appears in the left menu
    :var permissions: a list of named permissions used by the app
    :var sitemap: a list of :class:`SitemapEntries <allura.app.SitemapEntry>` to create an app navigation.
    :var bool installable: toggle if the app can be installed in a project
    :var bool hidden: toggle if the app should be hidden from the list of tools
    :var tool_description: tool's description that will be displayed to forge users
    :var Controller self.root: the root Controller used for the app
    :var Controller self.api_root: a Controller used for API access at /rest/<neighborhood>/<project>/<app>/
    :var Controller self.admin: a Controller used in the admin interface
    :var icons: a dictionary mapping icon sizes to application-specific icons paths
    """

    __version__ = None
    config_options = [
        ConfigOption('mount_point', str, 'app'),
        ConfigOption('mount_label', str, 'app'),
        ConfigOption('ordinal', int, '0') ]
    status_map = [ 'production', 'beta', 'alpha', 'user' ]
    status='production'
    script_name=None
    root=None  # root controller
    api_root=None
    permissions=[]
    sitemap = [ ]
    installable=True
    searchable = False
    DiscussionClass = model.Discussion
    PostClass = model.Post
    AttachmentClass = model.DiscussionAttachment
    tool_label='Tool'
    tool_description="This is a tool for Allura forge."
    default_mount_label='Tool Name'
    default_mount_point='tool'
    ordinal=0
    hidden = False
    icons={
        24:'images/admin_24.png',
        32:'images/admin_32.png',
        48:'images/admin_48.png'
    }

    def __init__(self, project, app_config_object):
        self.project = project
        self.config = app_config_object
        self.admin = DefaultAdminController(self)

    @LazyProperty
    def url(self):
        return self.config.url(project=self.project)

    @property
    def acl(self):
        return self.config.acl

    def parent_security_context(self):
        return self.config.parent_security_context()

    @classmethod
    def status_int(self):
        return self.status_map.index(self.status)

    @classmethod
    def icon_url(self, size):
        '''Subclasses (tools) provide their own icons (preferred) or in
        extraordinary circumstances override this routine to provide
        the URL to an icon of the requested size specific to that tool.

        Application.icons is simply a default if no more specific icon
        is available.
        '''
        resource = self.icons.get(size)
        if resource:
            return g.theme_href(resource)
        return ''

    def has_access(self, user, topic):
        '''Whether the user has access to send email to the given topic'''
        return False

    def is_visible_to(self, user):
        """Return whether ``user`` can view this app.

        :param user: user to check
        :type user: :class:`allura.model.User` instance
        :rtype: bool

        """
        return has_access(self, 'read')(user=user)

    def subscribe_admins(self):
        for uid in g.credentials.userids_with_named_role(self.project._id, 'Admin'):
            model.Mailbox.subscribe(
                type='direct',
                user_id=uid,
                project_id=self.project._id,
                app_config_id=self.config._id)

    def subscribe(self, user):
        if user and user != model.User.anonymous():
            model.Mailbox.subscribe(
                    type='direct',
                    user_id=user._id,
                    project_id=self.project._id,
                    app_config_id=self.config._id)

    @classmethod
    def default_options(cls):
        ":return: the default config options"
        return dict(
            (co.name, co.default)
            for co in cls.config_options)

    def install(self, project):
        'Whatever logic is required to initially set up a tool'
        # Create the discussion object
        discussion = self.DiscussionClass(
            shortname=self.config.options.mount_point,
            name='%s Discussion' % self.config.options.mount_point,
            description='Forum for %s comments' % self.config.options.mount_point)
        session(discussion).flush()
        self.config.discussion_id = discussion._id
        self.subscribe_admins()

    def uninstall(self, project=None, project_id=None):
        'Whatever logic is required to tear down a tool'
        if project_id is None: project_id = project._id
        # De-index all the artifacts belonging to this tool in one fell swoop
        g.solr.delete(q='project_id_s:"%s" AND mount_point_s:"%s"' % (
                project_id, self.config.options['mount_point']))
        for d in model.Discussion.query.find({
                'project_id':project_id,
                'app_config_id':self.config._id}):
            d.delete()
        self.config.delete()
        session(self.config).flush()

    @property
    def uninstallable(self):
        """Return True if this app can be uninstalled. Controls whether the
        'Delete' option appears on the admin menu for this app.

        By default, an app can be uninstalled iff it can be installed, although
        some apps may want/need to override this (e.g. an app which can
        not be installed directly by a user, but may be uninstalled).
        """
        return self.installable

    def main_menu(self):
        '''Apps should provide their entries to be added to the main nav
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        '''
        return self.sitemap

    def sidebar_menu(self):
        """
        Apps should override this to provide their menu
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        """
        return []

    def sidebar_menu_js(self):
        """
        Apps can override this to provide Javascript needed by the sidebar_menu.
        :return: a string of Javascript code
        """
        return ""

    def admin_menu(self, force_options=False):
        """
        Apps may override this to provide additional admin menu items
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        """
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = []
        if self.permissions and has_access(c.project, 'admin')():
            links.append(SitemapEntry('Permissions', admin_url + 'permissions'))
        if force_options or len(self.config_options) > 3:
            links.append(SitemapEntry('Options', admin_url + 'options', className='admin_modal'))
        links.append(SitemapEntry('Label', admin_url + 'edit_label', className='admin_modal'))
        return links

    def handle_message(self, topic, message):
        '''Handle incoming email msgs addressed to this tool'''
        pass

    def handle_artifact_message(self, artifact, message):
        # Find ancestor comment and thread
        thd, parent_id = artifact.get_discussion_thread(message)
        # Handle attachments
        message_id = message['message_id']
        if message.get('filename'):
            # Special case - the actual post may not have been created yet
            log.info('Saving attachment %s', message['filename'])
            fp = StringIO(message['payload'])
            self.AttachmentClass.save_attachment(
                message['filename'], fp,
                content_type=message.get('content_type', 'application/octet-stream'),
                discussion_id=thd.discussion_id,
                thread_id=thd._id,
                post_id=message_id,
                artifact_id=message_id)
            return
        # Handle duplicates
        post = self.PostClass.query.get(_id=message_id)
        if post:
            log.info('Existing message_id %s found - saving this as text attachment' % message_id)
            fp = StringIO(message['payload'])
            post.attach(
                'alternate', fp,
                content_type=message.get('content_type', 'application/octet-stream'),
                discussion_id=thd.discussion_id,
                thread_id=thd._id,
                post_id=message_id)
        else:
            text=message['payload'] or '--no text body--'
            post = thd.post(
                message_id=message_id,
                parent_id=parent_id,
                text=text,
                subject=message['headers'].get('Subject', 'no subject'))

class DefaultAdminController(BaseController):

    def __init__(self, app):
        self.app = app

    @expose()
    def index(self, **kw):
        permanent_redirect('permissions')

    @expose('jinja:allura:templates/app_admin_permissions.html')
    @without_trailing_slash
    def permissions(self):
        from ext.admin.widgets import PermissionCard
        c.card = PermissionCard()
        permissions = dict((p, []) for p in self.app.permissions)
        for ace in self.app.config.acl:
            if ace.access == model.ACE.ALLOW:
                try:
                    permissions[ace.permission].append(ace.role_id)
                except KeyError:
                    # old, unknown permission
                    pass
        return dict(
            app=self.app,
            allow_config=has_access(c.project, 'admin')(),
            permissions=permissions)

    @expose('jinja:allura:templates/app_admin_edit_label.html')
    def edit_label(self):
        return dict(
            app=self.app,
            allow_config=has_access(self.app, 'configure')())

    @expose()
    @require_post()
    def update_label(self, mount_label):
        require_access(self.app, 'configure')
        self.app.config.options['mount_label'] = mount_label
        redirect(request.referer)

    @expose('jinja:allura:templates/app_admin_options.html')
    def options(self):
        return dict(
            app=self.app,
            allow_config=has_access(self.app, 'configure')())

    @expose()
    @require_post()
    def configure(self, **kw):
        with push_config(c, app=self.app):
            require_access(self.app, 'configure')
            is_admin = self.app.config.tool_name == 'admin'
            if kw.pop('delete', False):
                if is_admin:
                    flash('Cannot delete the admin tool, sorry....')
                    redirect('.')
                c.project.uninstall_app(self.app.config.options.mount_point)
                redirect('..')
            for opt in self.app.config_options:
                if opt in Application.config_options:
                    continue  # skip base options (mount_point, mount_label, ordinal)
                val = kw.get(opt.name, '')
                if opt.ming_type == bool:
                    val = asbool(val or False)
                elif opt.ming_type == int:
                    val = asint(val or 0)
                self.app.config.options[opt.name] = val
            if is_admin:
                # possibly moving admin mount point
                redirect('/'
                         + c.project._id
                         + self.app.config.options.mount_point
                         + '/'
                         + self.app.config.options.mount_point
                         + '/')
            else:
                redirect(request.referer)

    @without_trailing_slash
    @expose()
    @vardec
    @require_post()
    def update(self, card=None, **kw):
        self.app.config.acl = []
        for args in card:
            perm = args['id']
            new_group_ids = args.get('new', [])
            group_ids = args.get('value', [])
            if isinstance(new_group_ids, basestring):
                new_group_ids = [ new_group_ids ]
            if isinstance(group_ids, basestring):
                group_ids = [ group_ids ]
            role_ids = map(ObjectId, group_ids + new_group_ids)
            self.app.config.acl += [
                model.ACE.allow(r, perm) for r in role_ids]
        redirect(request.referer)
