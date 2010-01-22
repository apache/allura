#-*- python -*-
import logging
from mimetypes import guess_type

# Non-stdlib imports
import pkg_resources
from tg import tmpl_context
from tg import expose, validate, redirect
from tg import request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import g, c, request
from formencode import validators
from pymongo.bson import ObjectId

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib.helpers import push_config
from pyforge.lib.search import search
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole

# Local imports
from forgetracker import model
from forgetracker import version

from forgetracker.widgets.issue_form import issue_form

log = logging.getLogger(__name__)

class ForgeTrackerApp(Application):
    __version__ = version.__version__
    permissions = ['configure', 'read', 'write', 'comment']

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = TrackerAdminController(self)

    @audit('Issues.#')
    def auditor(self, routing_key, data):
        log.info('Auditing data from %s (%s)',
                 routing_key, self.config.options.mount_point)

    @react('Issues.#')
    def reactor(self, routing_key, data):
        log.info('Reacting to data from %s (%s)',
                 routing_key, self.config.options.mount_point)

    @property
    def sitemap(self):
        menu_id = 'ForgeTracker (%s)' % self.config.options.mount_point
        with push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def sidebar_menu(self):
        return [
            SitemapEntry('Home', self.config.url()),
            SitemapEntry('Search', self.config.url() + 'search'),
            SitemapEntry('New Issue', self.config.url() + 'new/'),
            ]

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgetracker', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'

        self.uninstall(project)
        # Give the installing user all the permissions
        pr = c.user.project_role()
        for perm in self.permissions:
              self.config.acl[perm] = [ pr._id ]
        self.config.acl['read'].append(
            ProjectRole.query.get(name='*anonymous')._id)
        self.config.acl['comment'].append(
            ProjectRole.query.get(name='*authenticated')._id)
        model.Globals(project_id=c.project._id, last_issue_num=0, status_names='open,unread,accepted,pending,closed')

    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        project_id = {'project_id':c.project._id}
        # mapper(model.Issue).remove(project_id)
        # mapper(model.Comment).remove(project_id)
        # mapper(model.Attachment).remove(project_id)
        # mapper(model.Globals).remove(project_id)


class RootController(object):

    @with_trailing_slash
    @expose('forgetracker.templates.index')
    def index(self):
        issues = model.Issue.query.find(dict(project_id=c.project._id)).sort('issue_num')
        return dict(issues=issues)

    @expose('forgetracker.templates.search')
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

    def _lookup(self, issue_num, *remainder):
        return IssueController(issue_num), remainder

    @with_trailing_slash
    @expose('forgetracker.templates.new_issue')
    def new(self, **kw):
        require(has_artifact_access('write'))
        tmpl_context.form = issue_form
        return dict(modelname='Issue',
            page='New Issue')

    @expose('forgetracker.templates.not_found')
    def not_found(self, **kw):
        return dict()

    @expose()
    def save_issue(self, issue_num, **post_data):
        require(has_artifact_access('write'))
        if request.method != 'POST':
            raise Exception('save_new must be a POST request')
        if issue_num:
            issue = model.Issue.query.get(project_id=c.project._id,
                                          issue_num=int(issue_num))
            if not issue:
                raise Exception('Issue number not found.')
            del post_data['issue_num']
        else:
            issue = model.Issue()
            issue.project_id = c.project._id
            issue.custom_fields = dict()
            globals = model.Globals.query.get(project_id=c.project._id)

            # FIX ME: need to lock around this increment or something
            globals.last_issue_num += 1
            post_data['issue_num'] = globals.last_issue_num
            # FIX ME

        for k,v in post_data.iteritems():
            setattr(issue, k, v)
        redirect(str(issue.issue_num))


class IssueController(object):

    def __init__(self, issue_num=None):
        if issue_num is not None:
            self.issue_num = int(issue_num)
            self.issue = model.Issue.query.get(project_id=c.project._id,
                                                    issue_num=self.issue_num)
            self.attachment = AttachmentsController(self.issue)
            self.comments = CommentController(self.issue)

    @with_trailing_slash
    @expose('forgetracker.templates.issue')
    def index(self, **kw):
        require(has_artifact_access('read', self.issue))
        if self.issue is not None:
            globals = model.Globals.query.get(project_id=c.project._id)
            return dict(issue=self.issue, globals=globals)
        else:
            redirect('not_found')

    @with_trailing_slash
    @expose('forgetracker.templates.edit_issue')
    def edit(self, **kw):
        require(has_artifact_access('write', self.issue))
        globals = model.Globals.query.get(project_id=c.project._id)
        return dict(issue=self.issue, globals=globals)

    @expose()
    def update_issue(self, **post_data):
        require(has_artifact_access('write', self.issue))
        if request.method != 'POST':
            raise Exception('update_issue must be a POST request')
        self.issue.summary = post_data['summary']
        self.issue.description = post_data['description']
        self.issue.assigned_to = post_data['assigned_to']
        self.issue.status = post_data['status']

        globals = model.Globals.query.get(project_id=c.project._id)
        if globals.custom_fields:
            for field in globals.custom_fields.split(','):
                self.issue.custom_fields[field] = post_data[field]
        redirect('edit')

    @expose()
    def attach(self, file_info=None):
        require(has_artifact_access('write', self.issue))
        filename = file_info.filename
        content_type = guess_type(filename)
        if content_type: content_type = content_type[0]
        else: content_type = 'application/octet-stream'
        with model.Attachment.create(
            content_type=content_type,
            filename=filename,
            issue_id=self.issue._id) as fp:
            while True:
                s = file_info.file.read()
                if not s: break
                fp.write(s)
        redirect('.')

class AttachmentsController(object):

    def __init__(self, issue):
        self.issue = issue

    def _lookup(self, filename, *args):
        return AttachmentController(filename), args

class AttachmentController(object):

    def _check_security(self):
        require(has_artifact_access('read', self.issue))

    def __init__(self, filename):
        self.filename = filename
        self.attachment = model.Attachment.query.get(filename=filename)
        self.issue = self.attachment.issue

    @expose()
    def index(self, delete=False, embed=False):
        if request.method == 'POST':
            require(has_artifact_access('write', self.issue))
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

class CommentController(object):

    def __init__(self, issue, comment_id=None):
        self.issue = issue
        self.comment_id = comment_id
        self.comment = model.Comment.query.get(_id=self.comment_id)

    @expose()
    def reply(self, text):
        require(has_artifact_access('comment', self.issue))
        if self.comment_id:
            c = self.comment.reply()
            c.text = text
        else:
            c = self.issue.reply()
            c.text = text
        redirect(request.referer)

    @expose()
    def delete(self):
#        require(lambda:c.user._id == self.comment.author()._id)
#        self.comment.text = '[Text deleted by commenter]'
        self.comment.delete()
        redirect(request.referer)

    def _lookup(self, next, *remainder):
        if self.comment_id:
            return CommentController(
                self.issue,
                self.comment_id + '/' + next), remainder
        else:
            return CommentController(
                self.issue, next), remainder


class TrackerAdminController(DefaultAdminController):

    @with_trailing_slash
    @expose('forgetracker.templates.admin')
    def index(self):
        globals = model.Globals.query.get(project_id=c.project._id)
        return dict(app=self.app, globals=globals)

    @expose()
    def update_issues(self, **post_data):
        pass

    @expose()
    def set_status_names(self, **post_data):
        globals = model.Globals.query.get(project_id=c.project._id)
        globals.status_names = post_data['status_names']
        redirect('.')

    @expose()
    def set_custom_fields(self, **post_data):
        globals = model.Globals.query.get(project_id=c.project._id)
        globals.custom_fields = post_data['custom_fields']
        redirect('.')
