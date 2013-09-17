import re
from datetime import datetime

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from formencode import validators as fev
from tg import (
        expose,
        validate,
        flash,
        redirect
        )
from tg.decorators import (
        with_trailing_slash,
        without_trailing_slash
        )

from allura import model as M
from allura.controllers import BaseController
from allura.lib import helpers as h
from allura.lib.decorators import require_post, task
from ming.orm import session, ThreadLocalORMSession
from pylons import tmpl_context as c
from pylons import app_globals as g

from . import GitHubProjectExtractor
from ..base import ToolImporter
from forgetracker.tracker_main import ForgeTrackerApp
from forgetracker import model as TM
from forgeimporters.base import ToolImportForm, ImportErrorHandler


@task(notifications_disabled=True)
def import_tool(**kw):
    importer = GitHubTrackerImporter()
    with ImportErrorHandler(importer, kw.get('project_name'), c.project):
        importer.import_tool(c.project, c.user, **kw)


class GitHubTrackerImportForm(ToolImportForm):
    gh_project_name = fev.UnicodeString(not_empty=True)
    gh_user_name = fev.UnicodeString(not_empty=True)


class GitHubTrackerImportController(BaseController):

    def __init__(self):
        self.importer = GitHubTrackerImporter()

    @property
    def target_app(self):
        return self.importer.target_app

    @with_trailing_slash
    @expose('jinja:forgeimporters.github:templates/tracker/index.html')
    def index(self, **kw):
        return dict(importer=self.importer,
                    target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(GitHubTrackerImportForm(ForgeTrackerApp), error_handler=index)
    def create(self, gh_project_name, gh_user_name, mount_point, mount_label, **kw):
        import_tool.post(
                project_name=gh_project_name,
                user_name=gh_user_name,
                mount_point=mount_point,
                mount_label=mount_label)
        flash('Ticket import has begun. Your new tracker will be available '
                'when the import is complete.')
        redirect(c.project.url() + 'admin/')


class GitHubTrackerImporter(ToolImporter):
    source = 'GitHub'
    target_app = ForgeTrackerApp
    controller = GitHubTrackerImportController
    tool_label = 'Issues'
    max_ticket_num = 0
    open_milestones = set()

    def import_tool(self, project, user, project_name, mount_point=None,
            mount_label=None, **kw):
        app = project.install_app('tickets', mount_point, mount_label,
                EnableVoting=False,
                open_status_names='Open',
                closed_status_names='Closed',
            )
        ThreadLocalORMSession.flush_all()
        extractor = GitHubProjectExtractor(
            '{}/{}'.format(kw['user_name'],project_name),
        )
        try:
            M.session.artifact_orm_session._get().skip_mod_date = True
            with h.push_config(c, user=M.User.anonymous(), app=app):
                for ticket_num, issue in extractor.iter_issues():
                    self.max_ticket_num = max(ticket_num, self.max_ticket_num)
                    ticket = TM.Ticket(
                        app_config_id=app.config._id,
                        custom_fields=dict(),
                        ticket_num=ticket_num)
                    self.process_fields(ticket, issue)
                    self.process_comments(extractor, ticket, issue)
                    self.process_events(extractor, ticket, issue)
                    self.process_milestones(ticket, issue)
                    session(ticket).flush(ticket)
                    session(ticket).expunge(ticket)
                app.globals.custom_fields = self.postprocess_milestones()
                app.globals.last_ticket_num = self.max_ticket_num
                ThreadLocalORMSession.flush_all()
            g.post_event('project_updated')
            app.globals.invalidate_bin_counts()
            return app
        finally:
            M.session.artifact_orm_session._get().skip_mod_date = False

    def parse_datetime(self, datetime_string):
        return datetime.strptime(datetime_string, '%Y-%m-%dT%H:%M:%SZ')

    def get_user_link(self, user):
        return u'[{0}](https://github.com/{0})'.format(user)

    def process_fields(self, ticket, issue):
        ticket.summary = issue['title']
        ticket.status = issue['state']
        ticket.created_date = self.parse_datetime(issue['created_at'])
        ticket.mod_date = self.parse_datetime(issue['updated_at'])
        if issue['assignee']:
            owner_line = '*Originally owned by:* {}\n'.format(issue['assignee']['login'])
        else:
            owner_line = ''
        # body processing happens here
        body, attachments = self._get_attachments(issue['body'])
        ticket.add_multiple_attachments(attachments)
        ticket.description = (
                u'*Originally created by:* {creator}\n'
                u'{owner}'
                u'\n'
                u'{body}').format(
                    creator=issue['user']['login'],
                    owner=owner_line,
                    body=body,
                )
        ticket.labels = [label['name'] for label in issue['labels']]

    def process_comments(self, extractor, ticket, issue):
        for comment in extractor.iter_comments(issue):
            body, attachments = self._get_attachments(comment['body'])
            if comment['user']:
                posted_by = u'*Originally posted by: [{0}](https://github.com/{0})*\n'.format(
                    comment['user']['login'])
                posted_by += body
                body = posted_by
            p = ticket.discussion_thread.add_post(
                    text = body,
                    ignore_security = True,
                    timestamp = self.parse_datetime(comment['created_at']),
                )
            p.add_multiple_attachments(attachments)

    def process_events(self, extractor, ticket, issue):
        for event in extractor.iter_events(issue):
            prefix = text = ''
            if event['event'] in ('reopened', 'closed'):
                prefix = '*Ticket changed by: {}*\n\n'.format(
                        self.get_user_link(event['actor']['login']))
            if event['event'] == 'reopened':
                text = '- **status**: closed --> open'
            elif event['event'] == 'closed':
                text = '- **status**: open --> closed'
            elif event['event'] == 'assigned':
                text = '- **assigned_to**: {}'.format(
                        self.get_user_link(event['actor']['login']))

            text = prefix + text
            if not text:
                continue
            ticket.discussion_thread.add_post(
                text = text,
                ignore_security = True,
                timestamp = self.parse_datetime(event['created_at'])
            )

    def process_milestones(self, ticket, issue):
        if issue['milestone']:
            title = issue['milestone']['title']
            due = None
            if issue['milestone']['due_on']:
                due = self.parse_datetime(issue['milestone']['due_on'])
            ticket.custom_fields = {
                '_milestone': title,
            }
            self.open_milestones.add((title, due,))

    def postprocess_milestones(self):
        global_milestones = {
            'milestones': [],
            'type': 'milestone',
            'name': '_milestone',
            'label': 'Milestone'
        }
        for milestone in self.open_milestones:
            global_milestones['milestones'].append({
                'name': milestone[0],
                'due_date': unicode(milestone[1].date()),
                'complete': False,
            })
        return [global_milestones]

    def _get_attachments(self, body):
        # at github, attachments are images only and are included into comment's body
        # usual syntax is
        # ![cdbpzjc5ex4](https://f.cloud.github.com/assets/979771/1027411/a393ab5e-0e70-11e3-8a38-b93a3df904cf.jpg)\r\n
        REGEXP = r'!\[[\w0-9]+?\]\(((?:https?:\/\/)?[\da-z\.-]+\.[a-z\.]{2,6}'\
            '(?:[\/\w\.-]+)*.(jpg|jpeg|png|gif))\)\r\n'
        attachments = []

        try:
            found_matches = re.finditer(REGEXP, body, re.IGNORECASE)
        except TypeError:
            found_matches = re.finditer(REGEXP, str(body), re.IGNORECASE)

        for i, match in enumerate(found_matches):
            # removing attach text from comment
            body = body.replace(match.group(0), '')
            # stripping url and extension
            attachments.append(Attachment(
                match.group(1),  # url
                'attach{}.{}'.format(i + 1, match.group(2)) # extension
            ))
        return (body, attachments)

class Attachment(object):
    def __init__(self, url, filename):
        self.url = url
        self.filename = filename
        self.type = None

    @property
    def file(self):
        fp_ish = GitHubProjectExtractor.urlopen(self.url)
        fp = StringIO(fp_ish.read())
        return fp
