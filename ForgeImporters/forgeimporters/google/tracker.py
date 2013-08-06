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

from pylons import tmpl_context as c
from ming.orm import session, ThreadLocalORMSession

from allura.lib import helpers as h

from forgetracker.tracker_main import ForgeTrackerApp
from forgetracker import model as TM
from ..base import ToolImporter
from . import GoogleCodeProjectExtractor


class GoogleCodeTrackerImporter(ToolImporter):
    source = 'Google Code'
    target_app = ForgeTrackerApp
    controller = None
    tool_label = 'Issues'

    field_types = defaultdict(lambda: 'string',
            milestone='milestone',
            priority='select',
            type='select',
        )

    def import_tool(self, project, user, project_name, mount_point=None,
            mount_label=None, **kw):
        c.app = project.install_app('tickets', mount_point, mount_label)
        ThreadLocalORMSession.flush_all()
        c.app.globals.open_status_names = 'New Accepted Started'
        c.app.globals.closed_status_names = 'Fixed Verified Invalid Duplicate WontFix Done'
        self.custom_fields = {}
        for issue in GoogleCodeProjectExtractor.iter_issues(project_name):
            ticket = TM.Ticket.new()
            self.process_fields(ticket, issue)
            self.process_labels(ticket, issue)
            self.process_comments(ticket, issue)
            session(ticket).flush(ticket)
            session(ticket).expunge(ticket)
        self.postprocess_custom_fields()
        ThreadLocalORMSession.flush_all()

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
        ticket.description = (
                u'*Originally created by:* [{creator.name}]({creator.link})\n'
                '*Originally owned by:* [{owner.name}]({owner.link})\n'
                '\n'
                '{body}').format(
                    creator=issue.get_issue_creator(),
                    owner=issue.get_issue_owner(),
                    body=issue.get_issue_description(),
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
            else:
                labels.add(label)
        ticket.labels = list(labels)
        ticket.custom_fields = {n: u', '.join(sorted(v)) for n,v in custom_fields.iteritems()}

    def process_comments(self, ticket, issue):
        for comment in issue.iter_comments():
            p = ticket.discussion_thread.add_post(
                    text = (
                        u'*Originally posted by:* [{author.name}]({author.link})\n'
                        '\n'
                        '{body}\n'
                        '\n'
                        '{updates}').format(
                            author=comment.author,
                            body=comment.body,
                            updates='\n'.join(
                                '**%s** %s' % (k,v)
                                for k,v in comment.updates.items()
                            ),
                    )
                )
            p.created_date = p.timestamp = datetime.strptime(comment.created_date, '%c')
            p.add_multiple_attachments(comment.attachments)

    def postprocess_custom_fields(self):
        c.app.globals.custom_fields = []
        for name, field in self.custom_fields.iteritems():
            if field['name'] == '_milestone':
                field['milestones'] = [{
                        'name': milestone,
                        'due_date': None,
                        'complete': False,
                    } for milestone in field['options']]
                field['options'] = ''
            elif field['type'] == 'select':
                field['options'] = ' '.join(field['options'])
            else:
                field['options'] = ''
            c.app.globals.custom_fields.append(field)
