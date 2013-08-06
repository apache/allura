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
#import gdata
gdata = None
from ming.orm import session

from allura.lib import helpers as h

from forgetracker.tracker_main import ForgeTrackerApp
from forgetracker import model as TM
from ..base import ToolImporter


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

    def import_tool(self, project, project_name, mount_point=None, mount_label=None):
        c.app = project.install_app('tracker', mount_point, mount_label)
        c.app.globals.open_status_names = ['New', 'Accepted', 'Started']
        c.app.globals.closed_status_names = ['Fixed', 'Verified', 'Invalid', 'Duplicate', 'WontFix', 'Done']
        self.custom_fields = {}
        extractor = GDataAPIExtractor(project_name)
        for issue in extractor.iter_issues():
            ticket = TM.Ticket.new()
            self.process_fields(ticket, issue)
            self.process_labels(ticket, issue)
            self.process_comments(ticket, extractor.iter_comments(issue))
            session(ticket).flush(ticket)
            session(ticket).expunge(ticket)
        self.postprocess_custom_fields()
        session(c.app).flush(c.app)
        session(c.app.globals).flush(c.app.globals)

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
        ticket.summary = issue.summary
        ticket.description = issue.description
        ticket.status = issue.status
        ticket.created_date = datetime.strptime(issue.created_date, '')
        ticket.mod_date = datetime.strptime(issue.mod_date, '')

    def process_labels(self, ticket, issue):
        labels = set()
        custom_fields = defaultdict(set)
        for label in issue.labels:
            if u'-' in label:
                name, value = label.split(u'-', 1)
                cf = self.custom_field(name)
                cf['options'].add(value)
                custom_fields[cf['name']].add(value)
            else:
                labels.add(label)
        ticket.labels = list(labels)
        ticket.custom_fields = {n: u', '.join(sorted(v)) for n,v in custom_fields.iteritems()}

    def process_comments(self, ticket, comments):
        for comment in comments:
            p = ticket.thread.add_post(
                    text = (
                        u'Originally posted by: [{author.name}]({author.link})\n'
                        '\n'
                        '{body}\n'
                        '\n'
                        '{updates}').format(
                            author=comment.author,
                            body=comment.text,
                            updates='\n'.join(
                                '*%s*: %s' % (k,v)
                                for k,v in comment.updates.items()
                            ),
                    )
                )
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


class GDataAPIExtractor(object):
    def __init__(self, project_name):
        self.project_name = project_name

    def iter_issues(self, limit=50):
        """
        Iterate over all issues for a project,
        using paging to keep the responses reasonable.
        """
        start = 1

        client = gdata.projecthosting.client.ProjectHostingClient()
        while True:
            query = gdata.projecthosting.client.Query(start_index=start, max_results=limit)
            issues = client.get_issues(self.project_name, query=query).entry
            if len(issues) <= 0:
                return
            for issue in issues:
                yield GDataAPIIssue(issue)
            start += limit

    def iter_comments(self, issue, limit=50):
        """
        Iterate over all comments for a given issue,
        using paging to keep the responses reasonable.
        """
        start = 1

        client = gdata.projecthosting.client.ProjectHostingClient()
        while True:
            query = gdata.projecthosting.client.Query(start_index=start, max_results=limit)
            comments = client.get_comments(self.project_name, query=query).entry
            if len(comments) <= 0:
                return
            for comment in comments:
                yield GDataAPIComment(comment)
            start += limit


class GDataAPIUser(object):
    def __init__(self, user):
        self.user = user

    @property
    def name(self):
        return h.really_unicode(self.user.name.text)

    @property
    def link(self):
        return u'http://code.google.com/u/%s' % self.name


class GDataAPIIssue(object):
    def __init__(self, issue):
        self.issue = issue

    @property
    def summary(self):
        return h.really_unicode(self.issue.title.text)

    @property
    def description(self):
        return h.really_unicode(self.issue.content.text)

    @property
    def created_date(self):
        return self.to_date(self.issue.published.text)

    @property
    def mod_date(self):
        return self.to_date(self.issue.updated.text)

    @property
    def creator(self):
        return h.really_unicode(self.issue.author[0].name.text)

    @property
    def status(self):
        if getattr(self.issue, 'status', None) is not None:
            return h.really_unicode(self.issue.status.text)
        return u''

    @property
    def owner(self):
        if getattr(self.issue, 'owner', None) is not None:
            return h.really_unicode(self.issue.owner.username.text)
        return u''

    @property
    def labels(self):
        return [h.really_unicode(l.text) for l in self.issue.labels]


class GDataAPIComment(object):
    def __init__(self, comment):
        self.comment = comment

    @property
    def author(self):
        return GDataAPIUser(self.comment.author[0])

    @property
    def created_date(self):
        return h.really_unicode(self.comment.published.text)

    @property
    def body(self):
        return h.really_unicode(self.comment.content.text)

    @property
    def updates(self):
        return {}

    @property
    def attachments(self):
        return []


class GDataAPIAttachment(object):
    def __init__(self, attachment):
        self.attachment = attachment

    @property
    def filename(self):
        pass

    @property
    def type(self):
        pass

    @property
    def file(self):
        pass
