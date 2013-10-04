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

from collections import defaultdict
from datetime import datetime

from formencode import validators as fev

from pylons import tmpl_context as c
from pylons import app_globals as g
from ming.orm import session, ThreadLocalORMSession

from tg import (
        expose,
        flash,
        redirect,
        validate,
        )
from tg.decorators import (
        with_trailing_slash,
        without_trailing_slash,
        )

from allura.controllers import BaseController
from allura.lib import helpers as h
from allura.lib.plugin import ImportIdConverter
from allura.lib.decorators import require_post
from allura import model as M

from forgetracker.tracker_main import ForgeTrackerApp
from forgetracker import model as TM
from forgeimporters.google import GoogleCodeProjectExtractor
from forgeimporters.base import (
        ToolImporter,
        ToolImportForm,
        )


class GoogleCodeTrackerImportForm(ToolImportForm):
    gc_project_name = fev.UnicodeString(not_empty=True)


class GoogleCodeTrackerImportController(BaseController):
    def __init__(self):
        self.importer = GoogleCodeTrackerImporter()

    @property
    def target_app(self):
        return self.importer.target_app

    @with_trailing_slash
    @expose('jinja:forgeimporters.google:templates/tracker/index.html')
    def index(self, **kw):
        return dict(importer=self.importer,
                target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(GoogleCodeTrackerImportForm(ForgeTrackerApp), error_handler=index)
    def create(self, gc_project_name, mount_point, mount_label, **kw):
        if self.importer.enforce_limit(c.project):
            self.importer.post(
                    project_name=gc_project_name,
                    mount_point=mount_point,
                    mount_label=mount_label,
                    )
            flash('Ticket import has begun. Your new tracker will be available '
                    'when the import is complete.')
        else:
            flash('There are too many imports pending at this time.  Please wait and try again.', 'error')
        redirect(c.project.url() + 'admin/')


class GoogleCodeTrackerImporter(ToolImporter):
    source = 'Google Code'
    target_app = ForgeTrackerApp
    controller = GoogleCodeTrackerImportController
    tool_label = 'Issues'

    field_types = defaultdict(lambda: 'string',
            milestone='milestone',
            priority='select',
            type='select',
        )

    def __init__(self, *args, **kwargs):
        super(GoogleCodeTrackerImporter, self).__init__(*args, **kwargs)
        self.open_milestones = set()
        self.custom_fields = {}
        self.max_ticket_num = 0

    def import_tool(self, project, user, project_name, mount_point=None,
            mount_label=None, **kw):
        import_id_converter = ImportIdConverter.get()
        app = project.install_app('tickets', mount_point, mount_label,
                EnableVoting=True,
                open_status_names='New Accepted Started',
                closed_status_names='Fixed Verified Invalid Duplicate WontFix Done',
                import_id={
                        'source': self.source,
                        'project_name': project_name,
                    },
            )
        ThreadLocalORMSession.flush_all()
        try:
            M.session.artifact_orm_session._get().skip_mod_date = True
            with h.push_config(c, user=M.User.anonymous(), app=app):
                for ticket_num, issue in GoogleCodeProjectExtractor.iter_issues(project_name):
                    self.max_ticket_num = max(ticket_num, self.max_ticket_num)
                    ticket = TM.Ticket(
                        app_config_id=app.config._id,
                        custom_fields=dict(),
                        ticket_num=ticket_num,
                        import_id=import_id_converter.expand(ticket_num, app))
                    self.process_fields(ticket, issue)
                    self.process_labels(ticket, issue)
                    self.process_comments(ticket, issue)
                    session(ticket).flush(ticket)
                    session(ticket).expunge(ticket)
                app.globals.custom_fields = self.postprocess_custom_fields()
                app.globals.last_ticket_num = self.max_ticket_num
                ThreadLocalORMSession.flush_all()
            M.AuditLog.log(
                    'import tool %s from %s on %s' % (
                            app.config.options.mount_point,
                            project_name, self.source,
                        ),
                    project=project,
                    user=user,
                    url=app.url,
                )
            g.post_event('project_updated')
            app.globals.invalidate_bin_counts()
            return app
        except Exception as e:
            h.make_app_admin_only(app)
            raise
        finally:
            M.session.artifact_orm_session._get().skip_mod_date = False

    def custom_field(self, name):
        if name not in self.custom_fields:
            self.custom_fields[name] = {
                    'type': self.field_types[name.lower()],
                    'label': name,
                    'name': u'_%s' % name.lower(),
                    'options': set(),
                }
        return self.custom_fields[name]

    def process_fields(self, ticket, issue):
        ticket.summary = issue.get_issue_summary()
        ticket.status = issue.get_issue_status()
        ticket.created_date = datetime.strptime(issue.get_issue_created_date(), '%c')
        ticket.mod_date = datetime.strptime(issue.get_issue_mod_date(), '%c')
        ticket.votes_up = issue.get_issue_stars()
        ticket.votes = issue.get_issue_stars()
        owner = issue.get_issue_owner()
        if owner:
            owner_line = '*Originally owned by:* {owner}\n'.format(owner=owner)
        else:
            owner_line = ''
        ticket.description = (
                u'*Originally created by:* {creator}\n'
                u'{owner}'
                u'\n'
                u'{body}').format(
                    creator=issue.get_issue_creator(),
                    owner=owner_line,
                    body=h.plain2markdown(issue.get_issue_description(), preserve_multiple_spaces=True, has_html_entities=True),
                )
        ticket.add_multiple_attachments(issue.get_issue_attachments())

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
