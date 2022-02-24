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

import json
import re

from ming.orm import session
from tg import tmpl_context as c
from tg import app_globals as g
from tg import (
    expose,
    flash,
    redirect,
)
from tg.decorators import (
    with_trailing_slash,
    without_trailing_slash,
)

from allura.lib.decorators import require_post
from allura.lib import validators as v
from allura.lib import helpers as h
from allura.model import AuditLog
from allura.scripts.trac_export import (
    export,
    DateJSONEncoder,
)

from forgeimporters.base import (
    ToolImporter,
    ToolImportForm,
    ToolImportController,
)
from forgeimporters.trac import TracURLValidator
from forgetracker.import_support import ImportSupport
from forgetracker import model as TM


class TracTicketImportForm(ToolImportForm):
    trac_url = TracURLValidator()
    user_map = v.UserMapJsonFile(as_string=True)


class TracTicketImportController(ToolImportController):
    import_form = TracTicketImportForm

    @with_trailing_slash
    @expose('jinja:forgeimporters.trac:templates/tickets/index.html')
    def index(self, **kw):
        return dict(importer=self.importer,
                    target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    def create(self, trac_url, mount_point, mount_label, user_map=None, **kw):
        if self.importer.enforce_limit(c.project):
            self.importer.post(
                project_name=trac_url,
                mount_point=mount_point,
                mount_label=mount_label,
                trac_url=trac_url,
                user_map=user_map)
            flash('Ticket import has begun. Your new tracker will be '
                  'available when the import is complete.')
        else:
            flash(
                'There are too many imports pending at this time.  Please '
                'wait and try again.', 'error')
        redirect(c.project.url() + 'admin/')


class TracTicketImporter(ToolImporter):
    target_app_ep_names = 'tickets'
    source = 'Trac'
    controller = TracTicketImportController
    tool_label = 'Tickets'
    tool_description = 'Import your tickets from Trac'

    def import_tool(self, project, user, project_name=None, mount_point=None,
                    mount_label=None, trac_url=None, user_map=None, **kw):
        """ Import Trac tickets into a new Allura Tracker tool.

        """
        mount_point = mount_point or 'tickets'
        app = project.install_app(
            'Tickets',
            mount_point=mount_point,
            mount_label=mount_label or 'Tickets',
            open_status_names='new assigned accepted reopened',
            closed_status_names='closed',
            import_id={
                'source': self.source,
                'trac_url': trac_url,
            },
        )
        session(app.config).flush(app.config)
        session(app.globals).flush(app.globals)
        try:
            with h.push_config(c, app=app):
                TracImportSupport().perform_import(
                    json.dumps(export(trac_url), cls=DateJSONEncoder),
                    json.dumps({
                        'user_map': json.loads(user_map) if user_map else {},
                        'usernames_match': self.usernames_match(trac_url),
                    }),
                )
            AuditLog.log(
                'import tool {} from {}'.format(
                    app.config.options.mount_point,
                    trac_url,
                ),
                project=project, user=user, url=app.url,
            )
            g.post_event('project_updated')
            return app
        except Exception:
            h.make_app_admin_only(app)
            raise

    def usernames_match(self, trac_url):
        """Return True if the usernames in the source Trac match the usernames
        in the destination Allura instance.

        If this is True, Trac usernames will be mapped to their Allura
        counterparts regardless of whether a user_map file is supplied.

        If this is False, any Trac username not present in the user_map file
        (or if no file is supplied) will be assumed an unknown or non-existent
        user in the Allura instance.

        """
        return False


class TracImportSupport(ImportSupport):

    """Provides Trac-specific ticket and comment text processing."""

    def ticket_link(self, m):
        return '(%s)' % m.groups()[0]

    def get_slug_by_id(self, ticket, comment):
        """Given the id of an imported Trac comment, return it's Allura slug.

        """
        comment = int(comment)
        ticket = TM.Ticket.query.get(app_config_id=c.app.config._id,
                                     ticket_num=int(ticket))
        if not ticket:
            return ''
        comments = ticket.discussion_thread.post_class().query.find(dict(
            discussion_id=ticket.discussion_thread.discussion_id,
            thread_id=ticket.discussion_thread._id,
            status={'$in': ['ok', 'pending']},
            deleted=False)).sort('timestamp')

        if comment <= comments.count():
            return comments.all()[comment - 1].slug

    def comment_link(self, m):
        """Convert a Trac-style comment url to it's equivalent Allura url."""
        text, ticket, comment = m.groups()
        ticket = ticket.replace('\n', '')
        text = text.replace('\n', ' ')
        slug = self.get_slug_by_id(ticket, comment)
        if slug:
            return f'[{text}]({ticket}/#{slug})'
        else:
            return text

    def changeset_link(self, m):
        return '(r%s)' % m.group(1)

    def brackets_escaping(self, m):
        """Escape double brackets."""
        return r'[\[%s\]]' % m.groups()[0]

    def link_processing(self, text):
        """Fix up links in text imported from Trac::

            * Convert comment anchors from Trac ids to Allura slugs
            * Convert absolute links to Trac tickets into relative links to
              their Allura counterparts
            * Escape double-brackets

        """
        comment_pattern = re.compile(
            r'\[(\S*\s*\S*)\]\(\S*/(\d+\n*\d*)#comment:(\d+)\)')
        ticket_pattern = re.compile(r'(?<=\])\(\S*ticket/(\d+)(?:\?[^)]*)?\)')
        changeset_pattern = re.compile(
            r'(?<=\])\(\S*/changeset/(\d+)(?:\?[^]]*)?\)')
        brackets_pattern = re.compile(r'\[\[([^]]*)\]\]')

        text = comment_pattern.sub(self.comment_link, text)
        text = ticket_pattern.sub(self.ticket_link, text)
        text = changeset_pattern.sub(self.changeset_link, text)
        text = brackets_pattern.sub(self.brackets_escaping, text)
        return text

    def comment_processing(self, comment_text):
        """Modify comment text before comment is created."""
        return self.link_processing(comment_text)

    def description_processing(self, description_text):
        """Modify ticket description before ticket is created."""
        return self.link_processing(description_text)
