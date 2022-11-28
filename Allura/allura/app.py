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

import os
import logging
from six.moves.urllib_parse import urljoin
from io import BytesIO
from collections import defaultdict
from xml.etree import ElementTree as ET
from copy import copy

import pkg_resources
from tg import expose, redirect, flash, validate
from tg.decorators import without_trailing_slash
from tg import config as tg_config
from tg import request, app_globals as g, tmpl_context as c
from paste.deploy.converters import asbool, asint
from bson import ObjectId
from bson.errors import InvalidId
from formencode import validators as V
from webob import exc
from formencode import validators as fev

from ming.orm import session
from ming.utils import LazyProperty
import ew.jinja2_ew as ew

from allura.lib import helpers as h
from allura.lib.security import has_access, require_access
from allura import model
from allura.controllers import BaseController
from allura.lib.decorators import require_post, memoize
from allura.lib.utils import permanent_redirect, ConfigProxy
from allura import model as M
from allura.tasks import index_tasks
import six
from io import BytesIO
from allura.model.timeline import ActivityObject

log = logging.getLogger(__name__)

config = ConfigProxy(common_suffix='forgemail.domain')


class ConfigOption:

    """Definition of a configuration option for an :class:`Application`.

    """

    def __init__(self, name, ming_type, default,
                 label=None, help_text=None, validator=None,
                 extra_attrs=None):
        """Create a new ConfigOption."""
        self.name, self.ming_type, self._default, self.label = (
            name, ming_type, default, label or name)
        self.help_text = help_text
        self.validator = validator
        self.extra_attrs = extra_attrs

    @property
    def default(self):
        """Return the default value for this ConfigOption.

        """
        if callable(self._default):
            return self._default()
        return self._default

    def validate(self, value):
        if self.validator:
            return self.validator.to_python(value)
        return value

    def render_attrs(self):
        """Return extra_attrs formatted in a way that allows inserting into html tag"""
        return ew._Jinja2Widget().j2_attrs(self.extra_attrs or {})


class SitemapEntry:

    """A labeled URL, which may optionally have
    :class:`children <SitemapEntry>`.

    Used for generating trees of links.

    """

    def __init__(self, label, url=None, children=None, className=None,
                 ui_icon=None, small=None, tool_name=None, matching_urls=None, extra_html_attrs=None, mount_point=None):
        """
        Create a new SitemapEntry.

        :param label: the name
        :param url: the url
        :param children: optional, list of SitemapEntry objects
        :param className: optional, HTML class
        :param tool_name: optional, tool_name (used for top-level menu items)
        :param matching_urls: list of urls to consider "active" in menu display
        :param extra_html_attrs: dict to show as HTML attributes
        :param mount_point: used only for tracking project menu admin options
        """
        self.label = label
        self.className = className
        self.url = url
        self.small = small
        self.ui_icon = ui_icon
        self.children = children or []
        self.tool_name = tool_name
        self.mount_point = mount_point
        self.matching_urls = matching_urls or []
        self.extra_html_attrs = extra_html_attrs or {}

    def __getitem__(self, x):
        """Automatically expand the list of sitemap child entries with the
        given items.  Example::

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
        l.append('    children=%s' %
                 repr(self.children).replace('\n', '\n    '))
        l.append('>')
        return '\n'.join(l)

    def bind_app(self, app):
        """Recreate this SitemapEntry in the context of
        :class:`app <Application>`.

        :returns: :class:`SitemapEntry`

        """
        lbl = self.label
        url = self.url
        if callable(lbl):
            lbl = lbl(app)
        if url is not None:
            url = urljoin(app.url, url)
        return SitemapEntry(lbl, url,
                            [ch.bind_app(app) for ch in self.children],
                            className=self.className,
                            ui_icon=self.ui_icon,
                            small=self.small,
                            tool_name=self.tool_name,
                            matching_urls=self.matching_urls,
                            mount_point=app.config.options.mount_point,
                            extra_html_attrs=self.extra_html_attrs,
                            )

    def extend(self, sitemap_entries):
        """Extend our children with ``sitemap_entries``.

        :param sitemap_entries: list of :class:`SitemapEntry`

        For each entry, if it doesn't already exist in our children, add it.
        If it does already exist in our children, recursively extend the
        children or our copy with the children of the new copy.

        """
        child_index = {
            ch.label: ch for ch in self.children}
        for e in sitemap_entries:
            lbl = e.label
            match = child_index.get(e.label)
            if match and match.url == e.url:
                match.extend(e.children)
            else:
                self.children.append(e)
                child_index[lbl] = e

    def matches_url(self, request):
        """Return True if this SitemapEntry 'matches' the url of ``request``.

        """
        return self.url in request.upath_info or any([
            url in request.upath_info for url in self.matching_urls])

    def __json__(self):
        return dict(
            label=self.label,
            className=self.className,
            url=self.url,
            small=self.small,
            ui_icon=self.ui_icon,
            children=self.children,
            tool_name=self.tool_name,
            matching_urls=self.matching_urls,
            extra_html_attrs=self.extra_html_attrs,
        )


class Application(ActivityObject):

    """
    The base Allura pluggable application

    After extending this, expose the app by adding an entry point in your
    setup.py::

        [allura]
        myapp = foo.bar.baz:MyAppClass

    :cvar str status: One of 'production', 'beta', 'alpha', or 'user'. By
        default, only 'production' apps are installable in projects. Default
        is 'production'.
    :cvar bool searchable: If True, show search box in the left menu of this
        Application. Default is True.
    :cvar bool exportable: Default is False, Application can't be exported to json.
    :cvar list permissions: Named permissions used by instances of this
        Application. Default is [].
    :cvar dict permissions_desc: Descriptions of the named permissions.
    :cvar int max_instances: Specifies the number of tools of this type
        that can be added to the project. Zero indicates the system tool or one that
        can not be added to the project by the user. Default value is float("inf").
    :cvar bool hidden: Default is False, Application is not hidden from the
        list of a project's installed tools.
    :cvar bool has_notifications: Default is True, if set to False then application will not
        be listed on user subscriptions table.
    :cvar str tool_description: Text description of this Application.
    :cvar bool relaxed_mount_points: Set to True to relax the default mount point
        naming restrictions for this Application. Default is False. See
        :attr:`default mount point naming rules <allura.lib.helpers.re_tool_mount_point>` and
        :attr:`relaxed mount point naming rules <allura.lib.helpers.re_relaxed_tool_mount_point>`.
    :cvar Controller root: Serves content at
        /<neighborhood>/<project>/<app>/. Default is None - subclasses should
        override.
    :cvar Controller api_root: Serves API access at
        /rest/<neighborhood>/<project>/<app>/. Default is None - subclasses
        should override to expose API access to the Application.
    :cvar Controller admin_api_root: Serves Admin API access at
        /rest/<neighborhood>/<project>/admin/<app>/. Default is None -
        subclasses should override to expose Admin API access to the
        Application.
    :ivar Controller admin: Serves admin functions at
        /<neighborhood>/<project>/<admin>/<app>/. Default is a
        :class:`DefaultAdminController` instance.
    :cvar dict icons: Mapping of icon sizes to application-specific icon paths.
    :cvar list config_on_install: :class:`ConfigOption` names that should be
        configured by user during app installation
    """

    __version__ = None
    config_options = [
        ConfigOption('mount_point', str, 'app'),
        ConfigOption('mount_label', str, 'app'),
        ConfigOption('ordinal', int, '0')]
    config_on_install = []
    status_map = ['production', 'beta', 'alpha', 'user']
    status = 'production'
    script_name = None
    root = None  # root controller
    api_root = None
    admin_api_root = None
    permissions = []
    permissions_desc = {
        'unmoderated_post': 'Post comments without moderation.',
        'post': 'Post comments, subject to moderation.',
        'moderate': 'Approve and edit all comments.',
        'configure': 'Set label and options. Requires admin permission.',
        'admin': 'Set permissions.',
    }
    max_instances = float("inf")
    searchable = False
    exportable = False
    DiscussionClass = model.Discussion
    PostClass = model.Post
    AttachmentClass = model.DiscussionAttachment
    tool_label = 'Tool'
    tool_description = "This is a tool for Allura forge."
    default_mount_label = 'Tool Name'
    default_mount_point = 'tool'
    relaxed_mount_points = False
    ordinal = 0
    hidden = False
    has_notifications = True
    icons = {
        24: 'images/admin_24.png',
        32: 'images/admin_32.png',
        48: 'images/admin_48.png'
    }

    def __init__(self, project, app_config_object):
        """Create an Application instance.

        :param project: Project to which this Application belongs
        :type project: :class:`allura.model.project.Project`
        :param app_config_object: Config describing this Application
        :type app_config_object: :class:`allura.model.project.AppConfig`

        """
        self.project = project
        self.config = app_config_object
        self.admin = DefaultAdminController(self)

    @LazyProperty
    def sitemap(self):
        """Return a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        describing the page hierarchy provided by this Application.

        If the list is empty, the Application will not be displayed in the
        main project nav bar.

        """
        return [SitemapEntry(self.config.options.mount_label, '.')]

    @LazyProperty
    def url(self):
        """Return the URL for this Application.

        """
        return self.config.url(project=self.project)

    @LazyProperty
    def admin_url(self):
        return '{}{}/{}/'.format(
            self.project.url(), 'admin',
            self.config.options.mount_point)

    @property
    def email_address(self):
        """Return email address for this Application.

        Email address constructed from Application's url, and looks like this:

            wiki@test.p.in.domain.net

        where 'wiki@test.p' comes from app url (in this case /p/test/wiki/)
        and '.in.domain.net' comes from 'forgemail.domain' config entry.

        Assumes self.url returns a url path without domain, starting with '/'
        """
        if self.config.options.get('AllowEmailPosting', True):
            parts = list(reversed(self.url[1:-1].split('/')))
            return '{}@{}{}'.format(parts[0], '.'.join(parts[1:]), config.common_suffix)
        else:
            return tg_config.get('forgemail.return_path')

    @property
    def acl(self):
        """Return the :class:`Access Control List <allura.model.types.ACL>`
        for this Application.

        """
        return self.config.acl

    @classmethod
    def describe_permission(cls, permission):
        """Return help text describing what features ``permission`` controls.

        Subclasses should define :attr:`permissions_desc`,
        a ``{permission: description}`` mapping.

        Returns empty string if there is no description for ``permission``.

        """
        d = {}
        for t in reversed(cls.__mro__):
            d = dict(d, **getattr(t, 'permissions_desc', {}))
        return d.get(permission, '')

    def parent_security_context(self):
        """Return the parent of this object.

        Used for calculating permissions based on trees of ACLs.

        """
        return self.config.parent_security_context()

    @property
    def installable(self):
        """Checks whether to add a tool to the project.

        Return True if app can be installed.

        :rtype: bool

        """
        return self._installable(self.config.tool_name,
                                 self.project.neighborhood,
                                 self.project.app_configs,
                                 )

    @classmethod
    def _installable(cls, tool_name, nbhd, project_tools):
        if cls.installable is False:  # handle class level `installable = False` declarations
            return False
        if tool_name.lower() in nbhd.get_prohibited_tools():
            return False
        tools_list = [tool.tool_name.lower() for tool in project_tools]
        return tools_list.count(tool_name.lower()) < cls.max_instances

    @classmethod
    def validate_mount_point(cls, mount_point):
        """Check if ``mount_point`` is valid for this Application.

        In general, subclasses should not override this, but rather toggle
        the strictness of allowed mount point names by toggling
        :attr:`Application.relaxed_mount_points`.

        :param mount_point: the mount point to validate
        :type mount_point: str
        :rtype: A :class:`regex Match object <_sre.SRE_Match>` if the mount
                point is valid, else None

        """
        re = (h.re_relaxed_tool_mount_point if cls.relaxed_mount_points
              else h.re_tool_mount_point)
        return re.match(mount_point)

    @classmethod
    def status_int(self):
        """Return the :attr:`status` of this Application as an int.

        Used for sorting available Apps by status in the Admin interface.

        """
        return self.status_map.index(self.status)

    @classmethod
    def icon_url(cls, size):
        """Return URL for icon of the given ``size``.

        Subclasses can define their own icons by overriding
        :attr:`icons`.

        """
        resource, url = cls.icons.get(size), ''
        if resource:
            resource_path = os.path.join('nf', resource)
            url = (g.forge_static(resource) if cls.has_resource(resource_path)
                   else g.theme_href(resource))
        return url

    @classmethod
    @memoize
    def has_resource(cls, resource_path):
        """Determine whether this Application has the resource pointed to by
        ``resource_path``.

        If the resource is not found for the immediate class, its parents
        will be searched. The return value is the class that "owns" the
        resource, or None if the resource is not found.

        """
        for klass in [o for o in cls.__mro__ if issubclass(o, Application)]:
            if pkg_resources.resource_exists(klass.__module__, resource_path):
                return klass

    def has_access(self, user, topic):
        """Return True if ``user`` can send email to ``topic``.
        Default is False.

        :param user: :class:`allura.model.User` instance
        :param topic: str
        :rtype: bool

        """
        return False

    def is_visible_to(self, user):
        """Return True if ``user`` can view this app.

        :type user: :class:`allura.model.User` instance
        :rtype: bool

        """
        return has_access(self, 'read')(user=user)

    def subscribe_admins(self):
        """Subscribe all project Admins (for this Application's project) to the
        :class:`allura.model.notification.Mailbox` for this Application.

        """
        for uid in g.credentials.userids_with_named_role(self.project._id, 'Admin'):
            model.Mailbox.subscribe(
                type='direct',
                user_id=uid,
                project_id=self.project._id,
                app_config_id=self.config._id)

    def subscribe(self, user):
        """Subscribe :class:`user <allura.model.auth.User>` to the
        :class:`allura.model.notification.Mailbox` for this Application.

        """
        if user and user != model.User.anonymous():
            model.Mailbox.subscribe(
                type='direct',
                user_id=user._id,
                project_id=self.project._id,
                app_config_id=self.config._id)

    def unsubscribe(self, user):
        """Unsubscribe :class:`user <allura.model.auth.User>` to the
        :class:`allura.model.notification.Mailbox` for this Application.

        """
        if user and user != model.User.anonymous():
            model.Mailbox.unsubscribe(
                user_id=user._id,
                project_id=self.project._id,
                app_config_id=self.config._id)

    @classmethod
    def default_options(cls):
        """Return a ``(name, default value)`` mapping of this Application's
        :class:`config_options <ConfigOption>`.

        :rtype: dict

        """
        return {
            co.name: co.default
            for co in cls.config_options}

    @classmethod
    def options_on_install(cls):
        """
        Return a list of :class:`config_options <ConfigOption>` which should be
        configured by user during app installation.

        :rtype: list
        """
        return [o for o in cls.config_options
                if o.name in cls.config_on_install]

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
        if project_id is None:
            project_id = project._id
        # De-index all the artifacts belonging to this tool in one fell swoop
        index_tasks.solr_del_tool.post(project_id, self.config.options['mount_point'])

        for d in model.Discussion.query.find({
                'project_id': project_id,
                'app_config_id': self.config._id}):
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
        """Return a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        to display in the main project nav for this Application.

        Default implementation returns :attr:`sitemap` without any children.

        """
        sitemap_without_children = []
        for sm in self.sitemap:
            sm_copy = copy(sm)
            sm_copy.children = []
            sitemap_without_children.append(sm_copy)
        return sitemap_without_children

    def sitemap_xml(self):
        """Return a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        to add to the sitemap.xml for this Application.

        Default implementation returns the contents of :attr:`main_menu`
        :return:
        """
        return self.main_menu()

    def sidebar_menu(self):
        """Return a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        to render in the left sidebar for this Application.

        """
        return []

    def sidebar_menu_js(self):
        """Return Javascript needed by the sidebar menu of this Application.

        :return: a string of Javascript code

        """
        return ""

    @LazyProperty
    def _webhooks(self):
        """A list of webhooks that can be triggered by this app.

        :return: a list of :class:`WebhookSender <allura.webhooks.WebhookSender>`
        """
        tool_name = self.config.tool_name.lower()
        webhooks = [w for w in g.entry_points['webhooks'].values()
                    if tool_name in w.triggered_by]
        return webhooks

    def admin_menu(self, force_options=False):
        """Return the admin menu for this Application.

        Default implementation will return a menu with up to 4 links:

            - 'Permissions', if the current user has admin access to the
                project in which this Application is installed
            - 'Options', if this Application has custom options, or
                ``force_options`` is True
            - 'Rename', for editing this Application's label
            - 'Webhooks', if this Application can trigger any webhooks

        Subclasses should override this method to provide additional admin
        menu items.

        :param force_options: always include an 'Options' link in the menu,
            even if this Application has no custom options
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`

        """
        admin_url = c.project.url() + 'admin/' + \
            self.config.options.mount_point + '/'
        links = []
        if self.permissions and has_access(c.project, 'admin')():
            links.append(
                SitemapEntry('Permissions', admin_url + 'permissions'))
        if force_options or len(self.config_options) > 3:
            links.append(
                SitemapEntry('Options', admin_url + 'options', className='admin_modal'))
        links.append(
            SitemapEntry('Rename', admin_url + 'edit_label', className='admin_modal'))
        if len(self._webhooks) > 0:
            links.append(SitemapEntry('Webhooks', admin_url + 'webhooks'))
        return links

    @LazyProperty
    def admin_menu_collapse_button(self):
        """Returns button for showing/hiding admin sidebar menu"""
        return SitemapEntry(
            label=f'Admin - {self.config.options.mount_label}',
            extra_html_attrs={
                'id': 'sidebar-admin-menu-trigger',
            })

    @LazyProperty
    def admin_menu_delete_button(self):
        """Returns button for deleting an app if app can be deleted"""
        anchored_tools = self.project.neighborhood.get_anchored_tools()
        anchored = self.tool_label.lower() in list(anchored_tools.keys())
        if self.uninstallable and not anchored:
            return SitemapEntry(
                label='Delete Everything',
                url=self.admin_url + 'delete',
                className='admin_modal',
            )

    def handle_message(self, topic, message):
        """Handle incoming email msgs addressed to this tool.
        Default is a no-op.

        :param topic: portion of destination email address preceeding the '@'
        :type topic: str
        :param message: parsed email message
        :type message: dict - result of
            :func:`allura.lib.mail_util.parse_message`
        :rtype: None

        """
        pass

    def handle_artifact_message(self, artifact, message):
        """Handle message addressed to this Application.

        :param artifact: Specific artifact to which the message is addressed
        :type artifact: :class:`allura.model.artifact.Artifact`
        :param message: the message
        :type message: :class:`allura.model.artifact.Message`

        Default implementation posts the message to the appropriate discussion
        thread for the artifact.

        """
        # Find ancestor comment and thread
        thd, parent_id = artifact.get_discussion_thread(message)
        # Handle attachments
        message_id = message['message_id']
        if message.get('filename'):
            # Special case - the actual post may not have been created yet
            log.info('Saving attachment %s', message['filename'])
            fp = BytesIO(six.ensure_binary(message['payload']))
            self.AttachmentClass.save_attachment(
                message['filename'], fp,
                content_type=message.get(
                    'content_type', 'application/octet-stream'),
                discussion_id=thd.discussion_id,
                thread_id=thd._id,
                post_id=message_id,
                artifact_id=message_id)
            return
        # Handle duplicates (from multipart mail messages)
        post = self.PostClass.query.get(_id=message_id)
        if post:
            log.info(
                'Existing message_id %s found - saving this as text attachment' %
                message_id)

            fp = BytesIO(six.ensure_binary(message['payload']))
            post.attach(
                'alternate', fp,
                content_type=message.get(
                    'content_type', 'application/octet-stream'),
                discussion_id=thd.discussion_id,
                thread_id=thd._id,
                post_id=message_id)
        else:
            text = six.ensure_text(message['payload']) or '--no text body--'
            post = thd.post(
                message_id=message_id,
                parent_id=parent_id,
                text=text,
                subject=message['headers'].get('Subject', 'no subject'))

    def bulk_export(self, f, export_path='', with_attachments=False):
        """Export all artifacts in the tool into json file.

        :param f: File Object to write to

        Set exportable to True for applications implementing this.
        """
        raise NotImplementedError('bulk_export')

    def doap(self, parent):
        """App's representation for DOAP API.

        :param parent: Element to contain the results
        :type parent: xml.etree.ElementTree.Element or xml.etree.ElementTree.SubElement
        """
        feature = ET.SubElement(parent, 'sf:feature')
        feature = ET.SubElement(feature, 'sf:Feature')
        ET.SubElement(feature, 'name').text = self.config.options.mount_label
        ET.SubElement(feature, 'foaf:page', {'rdf:resource': h.absurl(self.url)})

    def __json__(self):
        """App's representation for JSON API.

        Returns dict that will be included in project's API under tools key.
        """
        json = {
            'name': self.config.tool_name,
            'mount_point': self.config.options.mount_point,
            'url': h.absurl(self.config.url()),
            'mount_label': self.config.options.mount_label
        }
        if self.api_root:
            json['api_url'] = h.absurl('/rest' + self.config.url())
        return json

    def get_attachment_export_path(self, path='', *args):
        return os.path.join(path, self.config.options.mount_point, *args)

    def make_dir_for_attachments(self, path):
        if not os.path.exists(path):
                os.makedirs(path)

    def save_attachments(self, path, attachments):
        self.make_dir_for_attachments(path)
        for attachment in attachments:
            attachment_path = os.path.join(
                path,
                os.path.basename(attachment.filename)
            )
            with open(attachment_path.encode('utf8', 'replace'), 'wb') as fl:
                fl.write(attachment.rfile().read())

    def default_redirect(self):
        """Redirect to url if first tool in a project. This method raises a
        redirect exception.

        """
        return None

    @property
    def activity_name(self):
        return self.config.options.mount_label

    @property
    def activity_url(self):
        return self.url

    @property
    def activity_extras(self):
        return {}


class AdminControllerMixin:
    """Provides common functionality admin controllers need"""
    def _before(self, *remainder, **params):
        # Display app's sidebar on admin page, instead of :class:`AdminApp`'s
        c.app = self.app


class DefaultAdminController(BaseController, AdminControllerMixin):

    """Provides basic admin functionality for an :class:`Application`.

    To add more admin functionality for your Application, extend this
    class and then assign an instance of it to the ``admin`` attr of
    your Application::

        class MyApp(Application):
            def __init__(self, *args):
                super(MyApp, self).__init__(*args)
                self.admin = MyAdminController(self)

    """

    def __init__(self, app):
        """Instantiate this controller for an :class:`app <Application>`.

        """
        super().__init__()
        self.app = app
        self.webhooks = WebhooksLookup(app)

    @expose()
    def index(self, **kw):
        """Home page for this controller.

        Redirects to the 'permissions' page by default.

        """
        permanent_redirect('permissions')

    @expose('json:')
    @require_post()
    def block_user(self, username, perm, reason=None, **kw):
        if not username or not perm:
            return dict(error='Enter username')
        user = model.User.by_username(username)
        if not user:
            return dict(error='User "%s" not found' % username)
        ace = model.ACE.deny(model.ProjectRole.by_user(user, upsert=True)._id, perm, reason)
        if not model.ACL.contains(ace, self.app.acl):
            self.app.acl.append(ace)
            model.AuditLog.log('{}: blocked user "{}" from permission "{}" for reason: "{}"'.format(
                self.app.config.options['mount_point'],
                username,
                ace.permission,
                reason,
            ))
            return dict(user_id=str(user._id), username=user.username, reason=reason)
        return dict(error='User "%s" already blocked' % user.username)

    @validate(dict(user_id=V.Set(),
                   perm=V.UnicodeString()))
    @expose('json:')
    @require_post()
    def unblock_user(self, user_id=None, perm=None, **kw):
        try:
            user_id = list(map(ObjectId, user_id))
        except InvalidId:
            user_id = []
        users = model.User.query.find({'_id': {'$in': user_id}}).all()
        if not users:
            return dict(error='Select user to unblock')
        unblocked = []
        for user in users:
            ace = model.ACE.deny(model.ProjectRole.by_user(user)._id, perm)
            ace = model.ACL.contains(ace, self.app.acl)
            if ace:
                self.app.acl.remove(ace)
                unblocked.append(str(user._id))
                model.AuditLog.log('{}: unblocked user "{}" from permission "{}"'.format(
                    self.app.config.options['mount_point'],
                    user.username,
                    ace.permission,
                ))
        return dict(unblocked=unblocked)

    @expose('jinja:allura:templates/app_admin_permissions.html')
    @without_trailing_slash
    def permissions(self):
        """Render the permissions management web page.

        """
        from .ext.admin.widgets import PermissionCard, BlockUser, BlockList
        c.card = PermissionCard()
        c.block_user = BlockUser()
        c.block_list = BlockList()
        permissions = {p: [] for p in self.app.permissions}
        block_list = defaultdict(list)
        for ace in self.app.config.acl:
            if ace.access == model.ACE.ALLOW:
                try:
                    permissions[ace.permission].append(ace.role_id)
                except KeyError:
                    # old, unknown permission
                    pass
            elif ace.access == model.ACE.DENY:
                role = model.ProjectRole.query.get(_id=ace.role_id)
                if role and role.name is None and role.user:
                    block_list[ace.permission].append((role.user, ace.reason))
        return dict(
            app=self.app,
            allow_config=has_access(c.project, 'admin')(),
            permissions=permissions,
            block_list=block_list)

    @expose('jinja:allura:templates/app_admin_edit_label.html')
    def edit_label(self):
        """Renders form to update the Application's ``mount_label``.

        """
        return dict(
            app=self.app,
            allow_config=has_access(self.app, 'configure')())

    @expose()
    @require_post()
    def update_label(self, mount_label):
        """Handles POST to update the Application's ``mount_label``.

        """
        require_access(self.app, 'configure')
        old_label = self.app.config.options['mount_label']
        self.app.config.options['mount_label'] = mount_label
        model.AuditLog.log('updated label: "{}" => "{}" for {}'.format(
            old_label,
            mount_label,
            self.app.config.options['mount_point']))
        g.post_event('project_menu_updated')
        redirect(six.ensure_text(request.referer or '/'))

    @expose('jinja:allura:templates/app_admin_options.html')
    def options(self):
        """Renders form to update the Application's ``config.options``.

        """
        return dict(
            app=self.app,
            allow_config=has_access(self.app, 'configure')())

    @expose('jinja:allura:templates/app_admin_delete.html')
    def delete(self):
        return dict(app=self.app)

    @expose()
    @require_post()
    def configure(self, **kw):
        """Handle POST to delete the Application or update its
        ``config.options``.

        """
        with h.push_config(c, app=self.app):
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
                    # skip base options (mount_point, mount_label, ordinal)
                    continue
                val = kw.get(opt.name, '')
                if opt.ming_type == bool:
                    val = asbool(val or False)
                elif opt.ming_type == int:
                    val = asint(val or 0)
                try:
                    val = opt.validate(val)
                except fev.Invalid as e:
                    flash(f'{opt.name}: {str(e)}', 'error')
                    continue
                if self.app.config.options[opt.name] != val:
                    M.AuditLog.log('{}: set option "{}" {} => {}'.format(
                        self.app.config.options['mount_point'],
                        opt.name,
                        self.app.config.options[opt.name],
                        val
                    ))
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
                redirect(six.ensure_text(request.referer or '/'))

    @without_trailing_slash
    @expose()
    @h.vardec
    @require_post()
    def update(self, card=None, **kw):
        """Handle POST to update permissions for the Application.

        """
        old_acl = self.app.config.acl
        self.app.config.acl = []
        for args in card:
            perm = args['id']
            new_group_ids = args.get('new', [])
            del_group_ids = []
            group_ids = args.get('value', [])
            if isinstance(new_group_ids, str):
                new_group_ids = [new_group_ids]
            if isinstance(group_ids, str):
                group_ids = [group_ids]

            for acl in old_acl:
                if (acl['permission'] == perm
                        and str(acl['role_id']) not in group_ids
                        and acl['access'] != model.ACE.DENY):
                    del_group_ids.append(str(acl['role_id']))

            def get_role(_id):
                return model.ProjectRole.query.get(_id=ObjectId(_id))
            groups = list(map(get_role, group_ids))
            new_groups = list(map(get_role, new_group_ids))
            del_groups = list(map(get_role, del_group_ids))

            def group_names(groups):
                return ', '.join((role.name or '<Unnamed>') for role in groups if role)

            if new_groups or del_groups:
                model.AuditLog.log('updated "{}" permission: "{}" => "{}" for {}'.format(
                    perm,
                    group_names(groups + del_groups),
                    group_names(groups + new_groups),
                    self.app.config.options['mount_point']))

            role_ids = list(map(ObjectId, group_ids + new_group_ids))
            self.app.config.acl += [
                model.ACE.allow(r, perm) for r in role_ids]

            # Add all ACEs for user roles back
            for ace in old_acl:
                if (ace.permission == perm) and (ace.access == model.ACE.DENY):
                    self.app.config.acl.append(ace)
        g.post_event('project_menu_updated')  # since 'read' permission changes can affect what is visible in menu
        redirect(six.ensure_text(request.referer or '/'))


class WebhooksLookup(BaseController, AdminControllerMixin):

    def __init__(self, app):
        super().__init__()
        self.app = app

    @without_trailing_slash
    @expose('jinja:allura:templates/app_admin_webhooks_list.html')
    def index(self, **kw):
        webhooks = self.app._webhooks
        if len(webhooks) == 0:
            raise exc.HTTPNotFound()
        configured_hooks = {}
        for hook in webhooks:
            configured_hooks[hook.type] = M.Webhook.query.find({
                'type': hook.type,
                'app_config_id': self.app.config._id}
            ).all()
        return {'webhooks': webhooks,
                'configured_hooks': configured_hooks,
                'admin_url': self.app.admin_url + 'webhooks'}

    @expose()
    def _lookup(self, name, *remainder):
        for hook in self.app._webhooks:
            if hook.type == name and hook.controller:
                return hook.controller(hook, self.app), remainder
        raise exc.HTTPNotFound(name)
