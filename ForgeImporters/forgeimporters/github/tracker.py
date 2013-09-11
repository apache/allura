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
                posted_by = u'*Originally posted by: [{0}](https://github.com/{0})*\n'.format(
                    comment['user']['login'])
                posted_by += body
                body = posted_by
            p = ticket.discussion_thread.add_post(
                    text = body,
                    ignore_security = True,
                    timestamp = datetime.strptime(comment['created_at'], '%Y-%m-%dT%H:%M:%SZ'),
                )
            p.add_multiple_attachments(attachments)

    def process_milestones(self, ticket, issue):
        if issue['milestone']:
            title = issue['milestone']['title']
            due = None
            if issue['milestone']['due_on']:
                due = datetime.strptime(issue['milestone']['due_on'], '%Y-%m-%dT%H:%M:%SZ')
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
