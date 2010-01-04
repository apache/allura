#-*- python -*-
import logging

# Non-stdlib imports
import pkg_resources
from tg import tmpl_context
from tg import expose, validate, redirect
from pylons import g, c, request
from formencode import validators
from pymongo.bson import ObjectId

from ming.orm.base import mapper

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry
from pyforge.lib.helpers import push_config
from pyforge.lib.search import search
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole

# Local imports
from forgetracker import model
from forgetracker import version

# from forgetracker.widgets.issue_form import create_issue_form

log = logging.getLogger(__name__)

class ForgeTrackerApp(Application):
    __version__ = version.__version__
    permissions = ['configure', 'read', 'write', 'comment']
    config_options = Application.config_options + [
        ConfigOption('some_str_config_option', str, 'some_str_config_option'),
        ConfigOption('some_int_config_option', int, 42),
        ]

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()

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
            SitemapEntry('Home', '.'),
            SitemapEntry('Search', 'search'),
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
            ProjectRole.m.get(name='*anonymous')._id)
        self.config.acl['comment'].append(
            ProjectRole.m.get(name='*authenticated')._id)
        self.config.m.save()
        globals = model.Globals.make({
            'project_id':c.project._id,
            'last_issue_num':0
        })
        globals.commit()

    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        project_id = {'project_id':c.project._id}
        # mapper(model.Issue).remove(project_id)
        # mapper(model.Comment).remove(project_id)
        # mapper(model.Attachment).remove(project_id)
        # mapper(model.Globals).remove(project_id)

class RootController(object):

    @expose('forgetracker.templates.index')
    def index(self):
        issues = model.Issue.m.find().all()
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

    @expose('forgetracker.templates.new_issue')
    def new(self, **kw):
        # require(has_artifact_access('create', ?))
        tmpl_context.form = create_issue_form
        return dict(modelname='Issue',
            page='New Issue')

class IssueController(object):

    def __init__(self, issue_num=None):
        self.issue_num  = issue_num
        self.issue      = model.Issue.m.get(issue_num=issue_num)
        self.comments   = CommentController(self.issue)

    @expose('forgetracker.templates.issue')
    def index(self, **kw):
        require(has_artifact_access('read', self.issue))
        return dict(issue=self.issue)



class CommentController(object):

    def __init__(self, issue, comment_id=None):
        self.issue = issue
        self.comment_id = comment_id
        self.comment = model.Comment.m.get(_id=self.comment_id)

    @expose()
    def reply(self, text):
        require(has_artifact_access('comment', self.artifact))
        if self.comment_id:
            c = self.comment.reply()
            c.text = text
        else:
            c = self.artifact.reply()
            c.text = text
        c.m.save()
        redirect(request.referer)

    @expose()
    def delete(self):
        require(lambda:c.user._id == self.comment.author()._id)
        self.comment.text = '[Text deleted by commenter]'
        self.comment.m.save()
        redirect(request.referer)

    def _lookup(self, next, *remainder):
        if self.comment_id:
            return CommentController(
                self.artifact,
                self.comment_id + '/' + next), remainder
        else:
            return CommentController(
                self.artifact, next), remainder
