from datetime import datetime

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
            project,
            '{}/{}'.format(kw['user_name'],project_name),
            'issues',
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
                    #self.process_labels(ticket, issue)
                    #self.process_comments(ticket, issue)
                    session(ticket).flush(ticket)
                    session(ticket).expunge(ticket)
                #app.globals.custom_fields = self.postprocess_custom_fields()
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
        ticket.description = (
                u'*Originally created by:* {creator}\n'
                u'{owner}'
                u'\n'
                u'{body}').format(
                    creator=issue['user']['login'],
                    owner=owner_line,
                    body=issue['body'],
                )

    def process_labels(self, ticket, issue):
        labels = set()
        custom_fields = defaultdict(set)
        for label in issue.get_issue_labels():
            if u'-' in label:
                name, value = label.split(u'-', 1)
                cf = self.custom_field(name)
                cf['options'].add(value)
                custom_fields[cf['name']].add(value)
                if cf['name'] == '_milestone' and ticket.status in c.app.globals.open_status_names:
                    self.open_milestones.add(value)
            else:
                labels.add(label)
        ticket.labels = list(labels)
        ticket.custom_fields = {n: u', '.join(sorted(v)) for n,v in custom_fields.iteritems()}

    def process_comments(self, ticket, issue):
        for comment in issue.iter_comments():
            p = ticket.discussion_thread.add_post(
                    text = comment.annotated_text,
                    ignore_security = True,
                    timestamp = datetime.strptime(comment.created_date, '%c'),
                )
            p.add_multiple_attachments(comment.attachments)

    def postprocess_custom_fields(self):
        custom_fields = []
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