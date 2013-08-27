import re
from datetime import datetime

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from allura import model as M
from allura.lib import helpers as h
from ming.orm import session, ThreadLocalORMSession
from pylons import tmpl_context as c
from pylons import app_globals as g

from . import GitHubProjectExtractor
from ..base import ToolImporter
from forgetracker.tracker_main import ForgeTrackerApp
from forgetracker import model as TM



class GitHubTrackerImporter(ToolImporter):
    source = 'GitHub'
    target_app = ForgeTrackerApp
    controller = None
    tool_label = 'Issues'
    max_ticket_num = 0

    def import_tool(self, project, user, project_name, mount_point=None,
            mount_label=None, **kw):
        app = project.install_app('tickets', mount_point, mount_label,
                EnableVoting=True,
                open_status_names='New Accepted',
                closed_status_names='Done',
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
                    session(ticket).flush(ticket)
                    session(ticket).expunge(ticket)
                #app.globals.custom_fields = self.get_milestones()
                app.globals.last_ticket_num = self.max_ticket_num
                ThreadLocalORMSession.flush_all()
            g.post_event('project_updated')
            app.globals.invalidate_bin_counts()
            return app
        finally:
            M.session.artifact_orm_session._get().skip_mod_date = False

    def process_fields(self, ticket, issue):
        ticket.summary = issue['title']
        ticket.status = issue['state']
        ticket.created_date = datetime.strptime(issue['created_at'], '%Y-%m-%dT%H:%M:%SZ')
        ticket.mod_date = datetime.strptime(issue['updated_at'], '%Y-%m-%dT%H:%M:%SZ')
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
                body += u'\n*Originally posted by: {}*'.format(comment['user']['login'])
            p = ticket.discussion_thread.add_post(
                    text = body,
                    ignore_security = True,
                    timestamp = datetime.strptime(comment['created_at'], '%Y-%m-%dT%H:%M:%SZ'),
                )
            p.add_multiple_attachments(attachments)

    def get_milestones(self):
        custom_fields = []
        milestones = []
        for name, field in self.custom_fields.iteritems():
            if field['name'] == '_milestone':
                field['milestones'] = [{
                        'name': milestone,
                        'due_date': None,
                        'complete': milestone not in self.open_milestones,
                    } for milestone in sorted(field['options'])]
                field['options'] = ''
            elif field['type'] == 'select':
                field['options'] = ' '.join(field['options'])
            else:
                field['options'] = ''
            custom_fields.append(field)
        return custom_fields

    def _get_attachments(self, body):
        # at github, attachments are images only and are included into comment's body
        # usual syntax is
        # ![cdbpzjc5ex4](https://f.cloud.github.com/assets/979771/1027411/a393ab5e-0e70-11e3-8a38-b93a3df904cf.jpg)\r\n
        REGEXP = r'!\[[\w0-9]+?\]\(((?:https?:\/\/)?[\da-z\.-]+\.[a-z\.]{2,6}'\
            '(?:[\/\w\.-]+)*.(jpg|jpeg|png|gif))\)\r\n'
        attachments = []
        found_matches = re.finditer(REGEXP, body, re.IGNORECASE)
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
