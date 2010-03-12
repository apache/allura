import logging

from tg import expose, redirect, flash
from pylons import c, g
from pymongo.bson import ObjectId

from ming.orm import session

from pyforge.lib.helpers import push_config
from pyforge.lib.security import require, has_artifact_access
from pyforge import model

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

class WSGIHook(object):

    def handles(self, environ):
        return False

    def __call__(self, environ, start_response):
        raise NotImplementedError, '__call__' # pragma no cover

class SitemapEntry(object):

    def __init__(self, label, url=None, children=None, className=None):
        self.label = label
        self.className = className
        self.url = url
        if children is None:
            children = []
        self.children = children

    def __getitem__(self, x):
        if isinstance(x, (list, tuple)):
            self.children.extend(list(x))
        else:
            self.children.append(x)
        return self

    def bind_app(self, app):
        lbl = self.label
        url = self.url
        if callable(lbl):
            lbl = lbl(app)
        if url is not None and not url.startswith('/'):
            url = app.url + url
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

class WidgetController(object):
    widgets=[]

    def __init__(self, app): pass

    def portlet(self, content):
        return '<div class="portlet">%s</div>' % content

class Application(object):
    'base pyforge pluggable application'
    __version__ = None
    config_options = [
        ConfigOption('mount_point', str, 'app') ]
    templates=None # path to templates
    script_name=None
    root=None  # root controller
    permissions=[]
    sitemap = [ ]
    installable=True
    wsgi = WSGIHook()
    widget = WidgetController
    DiscussionClass = model.Discussion
    PostClass = model.Post
    AttachmentClass = model.Attachment

    def __init__(self, project, app_config_object):
        self.project = project
        self.config = app_config_object # pragma: no cover
        self.admin = DefaultAdminController(self)
        self.url = self.config.url()

    def has_access(self, user, topic):
        '''Whether the user has access to send email to the given topic'''
        return False

    @classmethod
    def default_options(cls):
        return dict(
            (co.name, co.default)
            for co in cls.config_options)

    def install(self, project):
        'Whatever logic is required to initially set up a plugin'
        # Create the discussion object
        discussion = self.DiscussionClass(
            shortname=self.config.options.mount_point,
            name='%s Discussion' % self.config.options.mount_point,
            description='Forum for %s comments' % self.config.options.mount_point)
        session(discussion).flush()
        self.config.discussion_id = discussion._id

    def uninstall(self, project):
        'Whatever logic is required to tear down a plugin'
        # De-index all the artifacts belonging to this plugin in one fell swoop
        g.solr.delete('project_id_s:%s AND mount_point_s:%s' % (
                project._id, self.config.options['mount_point']))
        # Remove all tags referring to this plugin
        q_aref ={
            'artifact_ref.project_id':project._id,
            'artifact_ref.mount_point':self.config.options['mount_point']}
        model.Tag.query.remove(q_aref)
        model.TagEvent.query.remove(q_aref)
        model.UserTags.query.remove(q_aref)

    def sidebar_menu(self):
        return []

    def message_auditor(self, routing_key, data, artifact, **kw):
        # Find ancestor comment
        parent_id = data.get('in_reply_to', [ None ])[0]
        thd = artifact.discussion_thread(data)
        # Handle attachments
        message_id = data['message_id']
        if data.get('filename'):
            log.info('Saving attachment %s', data['filename'])
            self.AttachmentClass.save(data['filename'],
                                  data.get('content_type', 'application/octet-stream'),
                                  data['payload'],
                                  discussion_id=self.config.discussion_id,
                                  post_id=message_id)
            return
        # Handle duplicates
        original = self.PostClass.query.get(_id=message_id)
        if original:
            log.info('Saving text attachment')
            self.AttachmentClass.save('alternate',
                                  data.get('content_type', 'application/octet-stream'),
                                  data['payload'],
                                  discussion_id=self.config.discussion_id,
                                  post_id=message_id)
            return
        thd.post(
            text=data['payload'],
            message_id=message_id,
            parent_id=parent_id,
            **kw)


class DefaultAdminController(object):

    def __init__(self, app):
        self.app = app

    @expose('pyforge.templates.app_admin')
    def index(self):
        return dict(app=self.app,
                    allow_config=has_artifact_access('configure', app=self.app)())

    @expose()
    def configure(self, **kw):
        with push_config(c, app=self.app):
            require(has_artifact_access('configure', app=self.app), 'Must have configure permission')
            is_admin = self.app.config.plugin_name == 'admin'
            if kw.pop('delete', False):
                if is_admin:
                    flash('Cannot delete the admin plugin, sorry....')
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

    @expose()
    def add_perm(self, permission, role):
        require(has_artifact_access('configure', app=self.app))
        self.app.config.acl[permission].append(ObjectId(role))
        redirect('.#app-acl')

    @expose()
    def del_perm(self, permission, role):
        require(has_artifact_access('configure', app=self.app))
        self.app.config.acl[permission].remove(ObjectId(role))
        redirect('.#app-acl')
        

