import logging
from urllib import basejoin
from cStringIO import StringIO

from tg import expose, redirect, flash
from tg.decorators import without_trailing_slash
from pylons import c, g, request
from bson import ObjectId

from ming.orm import session

from allura.lib.helpers import push_config, vardec
from allura.lib.security import require, has_artifact_access, has_project_access
from allura import model
from allura.controllers import BaseController
from allura.lib.decorators import react, require_post

log = logging.getLogger(__name__)

class ConfigOption(object):

    def __init__(self, name, ming_type, default):
        self.name, self.ming_type, self._default = (
            name, ming_type, default)

    @property
    def default(self):
        if callable(self._default):
            return self._default()
        return self._default

class SitemapEntry(object):

    def __init__(self, label, url=None, children=None, className=None, ui_icon=None, small=None):
        self.label = label
        self.className = className
        self.url = url
        self.small = small
        self.ui_icon = ui_icon
        if children is None:
            children = []
        self.children = children

    def __getitem__(self, x):
        if isinstance(x, (list, tuple)):
            self.children.extend(list(x))
        else:
            self.children.append(x)
        return self

    def __repr__(self):
        l = ['<SitemapEntry ']
        l.append('    label=%r' % self.label)
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

class WidgetController(BaseController):
    widgets=[]

    def __init__(self, app): pass

    def portlet(self, content):
        return '<div class="portlet">%s</div>' % content

class Application(object):
    """
    The base Allura pluggable application

    :var status: the status level of this app.  'production' apps are available to all projects
    :var bool searchable: toggle if the search box appears in the left menu
    :var permissions: a list of named permissions used by the app
    :var sitemap: a list of :class:`SitemapEntries <allura.app.SitemapEntry>` to create an app navigation.
    :var bool installable: toggle if the app can be installed in a project
    :var Controller self.root: the root Controller used for the app
    :var Controller self.api_root: a Controller used for API access at /rest/<neighborhood>/<project>/<app>/
    :var Controller self.admin: a Controller used in the admin interface
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
    widget = WidgetController
    searchable = False
    DiscussionClass = model.Discussion
    PostClass = model.Post
    AttachmentClass = model.DiscussionAttachment
    tool_label='Tool'
    default_mount_label='Tool Name'
    default_mount_point='tool'
    ordinal=0
    icons={
        24:'allura/images/admin_24.png',
        32:'allura/images/admin_32.png',
        48:'allura/images/admin_48.png'
    }
    event_listeners={}

    def __init__(self, project, app_config_object):
        self.project = project
        self.config = app_config_object # pragma: no cover
        self.admin = DefaultAdminController(self)
        self.url = self.config.url()

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
            return g.forge_static(resource)
        return ''

    def has_access(self, user, topic):
        '''Whether the user has access to send email to the given topic'''
        return False

    def is_visible_to(self, user):
        '''Whether the user can view the app.'''
        return has_artifact_access('read', app=self)(user=user)

    @react('forge.project_updated')
    def subscribe_new_admin(self, routing_key, doc):
        if str(c.project._id) == doc['project_id']:
            self.subscribe_admins()

    def subscribe_admins(self):
        for uid in g.credentials.userids_with_named_role(self.project._id, 'Admin'):
            model.Mailbox.subscribe(
                type='direct',
                user_id=uid,
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

    def sidebar_menu(self):
        """
        Apps should override this to provide their menu
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        """
        return []

    def admin_menu(self):
        """
        Apps may override this to provide additional admin menu items
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        """
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = []
        if self.permissions and has_project_access('security')():
            links.append(SitemapEntry('Permissions', admin_url + 'permissions', className='nav_child'))
        if len(self.config_options) > 3:
            links.append(SitemapEntry('Options', admin_url + 'options', className='admin_modal'))
        return links

    def handle_message(self, topic, message):
        '''Handle incoming email msgs addressed to this tool'''
        pass

    def handle_artifact_message(self, artifact, message):
        # Find ancestor comment
        in_reply_to = message.get('in_reply_to', [])
        if in_reply_to:
            parent_id = in_reply_to[0]
        else:
            parent_id = None
        thd = artifact.get_discussion_thread(message)
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
            text=message['payload'] or '--no text body--',
            post = thd.post(
                message_id=message_id,
                parent_id=parent_id,
                text=text)

class DefaultAdminController(BaseController):

    def __init__(self, app):
        self.app = app

    @expose()
    def index(self, **kw):
        return redirect('permissions')

    @expose('jinja:allura:templates/app_admin_permissions.html')
    @without_trailing_slash
    def permissions(self):
        from ext.admin.widgets import PermissionCard
        c.card = PermissionCard()
        return dict(app=self.app,
                    allow_config=has_project_access('security')())

    @expose('jinja:allura:templates/app_admin_options.html')
    def options(self):
        return dict(app=self.app,
                    allow_config=has_artifact_access('configure', app=self.app)())

    @expose()
    @require_post()
    def configure(self, **kw):
        with push_config(c, app=self.app):
            require(has_artifact_access('configure', app=self.app), 'Must have configure permission')
            is_admin = self.app.config.tool_name == 'admin'
            if kw.pop('delete', False):
                if is_admin:
                    flash('Cannot delete the admin tool, sorry....')
                    redirect('.')
                c.project.uninstall_app(self.app.config.options.mount_point)
                redirect('..')
            for k,v in kw.iteritems():
                self.app.config.options[k] = v
            if is_admin:
                # possibly moving admin mount point
                redirect('/'
                         + c.project._id
                         + self.app.config.options.mount_point
                         + '/'
                         + self.app.config.options.mount_point
                         + '/')
            else:
                redirect('../' + self.app.config.options.mount_point + '/')

    @without_trailing_slash
    @expose()
    @vardec
    @require_post()
    def update(self, card=None, **kw):
        for args in card:
            perm = args['id']
            new_group_ids = args.get('new', [])
            group_ids = args.get('value', [])
            if isinstance(new_group_ids, basestring):
                new_group_ids = [ new_group_ids ]
            if isinstance(group_ids, basestring):
                group_ids = [ group_ids ]
            role_ids = map(ObjectId, group_ids + new_group_ids)
            roles = model.ProjectRole.query.find(dict(
                _id={'$in':role_ids},
                project_id=c.project.root_project._id))
            self.app.config.acl[perm] = [ r._id for r in roles ]
        redirect(request.referer)

    @expose()
    @require_post()
    def del_perm(self, permission=None, role=None):
        require(has_artifact_access('configure', app=self.app))
        self.app.config.acl[permission].remove(ObjectId(role))
        redirect('permissions')
