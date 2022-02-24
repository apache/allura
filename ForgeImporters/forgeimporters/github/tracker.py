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

import re
import logging
from datetime import datetime
from six.moves.urllib.error import HTTPError
import six
from io import BytesIO

from tg import (
    expose,
    flash,
    redirect
)
from tg.decorators import (
    with_trailing_slash,
    without_trailing_slash
)

from allura import model as M
from allura.lib import helpers as h
from allura.lib import validators as v
from allura.lib.plugin import ImportIdConverter
from allura.lib.decorators import require_post
from ming.orm import session, ThreadLocalORMSession
from tg import tmpl_context as c
from tg import app_globals as g

from forgetracker import model as TM
from forgeimporters.base import (
    ToolImporter,
    ToolImportForm,
    ToolImportController,
)
from forgeimporters.github import (
    GitHubProjectExtractor,
    GitHubOAuthMixin,
    GitHubProjectNameValidator,
)
from forgeimporters.github.utils import GitHubMarkdownConverter


log = logging.getLogger(__name__)


class GitHubTrackerImportForm(ToolImportForm):
    gh_project_name = GitHubProjectNameValidator()
    gh_user_name = v.UnicodeString(not_empty=True)


class GitHubTrackerImportController(ToolImportController, GitHubOAuthMixin):
    import_form = GitHubTrackerImportForm

    @with_trailing_slash
    @expose('jinja:forgeimporters.github:templates/tracker/index.html')
    def index(self, **kw):
        self.oauth_begin()
        return dict(importer=self.importer,
                    target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    def create(self, gh_project_name, gh_user_name, mount_point, mount_label, **kw):
        if self.importer.enforce_limit(c.project):
            self.importer.post(
                project_name=gh_project_name,
                user_name=gh_user_name,
                mount_point=mount_point,
                mount_label=mount_label)
            flash('Ticket import has begun. Your new tracker will be available '
                  'when the import is complete.')
        else:
            flash(
                'There are too many imports pending at this time.  Please wait and try again.', 'error')
        redirect(c.project.url() + 'admin/')


class GitHubTrackerImporter(ToolImporter):
    source = 'GitHub'
    target_app_ep_names = 'tickets'
    controller = GitHubTrackerImportController
    tool_label = 'Issues'
    max_ticket_num = 0
    open_milestones = set()

    def import_tool(self, project, user, project_name, mount_point=None,
                    mount_label=None, **kw):
        import_id_converter = ImportIdConverter.get()
        project_name = '{}/{}'.format(kw['user_name'], project_name)
        extractor = GitHubProjectExtractor(project_name, user=user)
        if not extractor.has_tracker():
            return
        app = project.install_app('tickets', mount_point, mount_label,
                                  EnableVoting=False,
                                  open_status_names='open',
                                  closed_status_names='closed',
                                  import_id={
                                      'source': self.source,
                                      'project_name': project_name,
                                  }
                                  )
        self.github_markdown_converter = GitHubMarkdownConverter(
            kw['user_name'], project_name)
        ThreadLocalORMSession.flush_all()
        try:
            M.session.artifact_orm_session._get().skip_mod_date = True
            with h.push_config(c, user=M.User.anonymous(), app=app):
                for ticket_num, issue in extractor.iter_issues():
                    self.max_ticket_num = max(ticket_num, self.max_ticket_num)
                    ticket = TM.Ticket(
                        app_config_id=app.config._id,
                        custom_fields=dict(),
                        ticket_num=ticket_num,
                        import_id=import_id_converter.expand(ticket_num, app)
                    )
                    self.process_fields(extractor, ticket, issue)
                    self.process_comments(extractor, ticket, issue)
                    self.process_events(extractor, ticket, issue)
                    self.process_milestones(ticket, issue)
                    session(ticket).flush(ticket)
                    session(ticket).expunge(ticket)
                app.globals.custom_fields = self.postprocess_milestones()
                app.globals.last_ticket_num = self.max_ticket_num
                ThreadLocalORMSession.flush_all()
            M.AuditLog.log(
                'import tool {} from {} on {}'.format(
                    app.config.options.mount_point,
                    project_name, self.source),
                project=project, user=user, url=app.url)
            g.post_event('project_updated')
            app.globals.invalidate_bin_counts()
            return app
        finally:
            M.session.artifact_orm_session._get().skip_mod_date = False

    def parse_datetime(self, datetime_string):
        return datetime.strptime(datetime_string, '%Y-%m-%dT%H:%M:%SZ')

    def get_user_link(self, user):
        return '[{0}](https://github.com/{0})'.format(user)

    def process_fields(self, extractor, ticket, issue):
        ticket.summary = issue['title']
        ticket.status = issue['state']
        ticket.created_date = self.parse_datetime(issue['created_at'])
        ticket.mod_date = self.parse_datetime(issue['updated_at'])
        if issue['assignee']:
            owner_line = '*Originally owned by:* {}\n'.format(
                self.get_user_link(issue['assignee']['login']))
        else:
            owner_line = ''
        # body processing happens here
        body, attachments = self._get_attachments(extractor, issue['body'])
        ticket.add_multiple_attachments(attachments)
        ticket.description = (
            '*Originally created by:* {creator}\n'
            '{owner}'
            '\n'
            '{body}').format(
            creator=self.get_user_link(issue['user']['login']),
            owner=owner_line,
            body=self.github_markdown_converter.convert(body),
        )
        ticket.labels = [label['name'] for label in issue['labels']]

    def process_comments(self, extractor, ticket, issue):
        for comment in extractor.iter_comments(issue):
            body, attachments = self._get_attachments(
                extractor, comment['body'])
            if comment['user']:
                posted_by = '*Originally posted by:* {}\n\n'.format(
                    self.get_user_link(comment['user']['login']))
                body = posted_by + body
            p = ticket.discussion_thread.add_post(
                text=self.github_markdown_converter.convert(body),
                ignore_security=True,
                timestamp=self.parse_datetime(comment['created_at']),
            )
            p.add_multiple_attachments(attachments)

    def process_events(self, extractor, ticket, issue):
        for event in extractor.iter_events(issue):
            prefix = text = ''
            actor = event['actor']
            if event['event'] in ('reopened', 'closed'):
                prefix = '*Ticket changed by:* {}\n\n'.format(
                    self.get_user_link(actor['login'] if actor else 'ghost'))
            if event['event'] == 'reopened':
                text = '- **status**: closed --> open'
            elif event['event'] == 'closed':
                text = '- **status**: open --> closed'
            elif event['event'] == 'assigned':
                text = '- **assigned_to**: {}'.format(
                    self.get_user_link(actor['login'] if actor else 'ghost'))

            text = prefix + text
            if not text:
                continue
            ticket.discussion_thread.add_post(
                text=text,
                ignore_security=True,
                timestamp=self.parse_datetime(event['created_at'])
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
                'due_date': str(milestone[1].date()) if milestone[1] else None,
                'complete': False,
            })
        return [global_milestones]

    def _get_attachments(self, extractor, body):
        # at github, attachments are images only and are included into comment's body
        # usual syntax is
        # ![cdbpzjc5ex4](https://f.cloud.github.com/assets/979771/1027411/a393ab5e-0e70-11e3-8a38-b93a3df904cf.jpg)\r\n
        REGEXP = r'!\[[\w0-9]+?\]\(((?:https?:\/\/)?[\da-z\.-]+\.[a-z\.]{2,6}'\
            '[\\/%\\w\\.-]*.(jpg|jpeg|png|gif))\\)[\r\n]*'
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
                extractor,
                match.group(1),  # url
                f'attach{i + 1}.{match.group(2)}'  # extension
            ))
        return (body, attachments)


class Attachment:

    def __init__(self, extractor, url, filename):
        self.url = url
        self.filename = filename
        self.type = None
        file = self.get_file(extractor)
        if file:
            # don't set unless valid (add_multiple_attachments uses hasattr)
            self.file = file

    def get_file(self, extractor):
        try:
            fp_ish = extractor.urlopen(self.url)
            fp = BytesIO(fp_ish.read())
            return fp
        except HTTPError as e:
            if e.code == 404:
                log.error('Unable to load attachment: %s', self.url)
                return None
            else:
                raise
