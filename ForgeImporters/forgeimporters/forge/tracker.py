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

import dateutil.parser
from tg import tmpl_context as c
from tg import app_globals as g
from ming.orm import session, ThreadLocalORMSession

from tg import (
    expose,
    flash,
    redirect,
)
from tg.decorators import (
    with_trailing_slash,
    without_trailing_slash,
)

from allura.lib import helpers as h
from allura.lib.plugin import ImportIdConverter
from allura.lib.decorators import require_post
from allura.lib import validators as v
from allura import model as M

from forgetracker import model as TM
from forgeimporters.base import (
    ToolImportForm,
    ToolImportController,
    File,
    save_importer_upload,
)
from forgeimporters.forge.alluraImporter import AlluraImporter


class ForgeTrackerImportForm(ToolImportForm):
    tickets_json = v.JsonFile(not_empty=True)


class ForgeTrackerImportController(ToolImportController):
    import_form = ForgeTrackerImportForm

    @with_trailing_slash
    @expose('jinja:forgeimporters.forge:templates/tracker/index.html')
    def index(self, **kw):
        return dict(importer=self.importer,
                    target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    def create(self, tickets_json, mount_point, mount_label, **kw):
        if self.importer.enforce_limit(c.project):
            save_importer_upload(
                c.project, 'tickets.json', json.dumps(tickets_json))
            self.importer.post(
                mount_point=mount_point,
                mount_label=mount_label,
            )
            flash('Ticket import has begun. Your new tracker will be available '
                  'when the import is complete.')
            redirect(c.project.url() + 'admin/')
        else:
            flash(
                'There are too many imports pending at this time.  Please wait and try again.', 'error')
        redirect(c.project.url() + 'admin/')


class ForgeTrackerImporter(AlluraImporter):
    source = 'Allura'
    target_app_ep_names = 'tickets'
    controller = ForgeTrackerImportController
    tool_label = 'Tickets'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_ticket_num = 0

    def _load_json(self, project):
        return self._load_json_by_filename(project, 'tickets.json')

    def import_tool(self, project, user, mount_point=None,
                    mount_label=None, **kw):
        import_id_converter = ImportIdConverter.get()
        tracker_json = self._load_json(project)
        tracker_json['tracker_config']['options'].pop('ordinal', None)
        tracker_json['tracker_config']['options'].pop('mount_point', None)
        tracker_json['tracker_config']['options'].pop('mount_label', None)
        tracker_json['tracker_config']['options'].pop('import_id', None)
        app = project.install_app('tickets', mount_point, mount_label,
                                  import_id={
                                      'source': self.source,
                                      'app_config_id': tracker_json['tracker_config']['_id'],
                                  },
                                  open_status_names=tracker_json[
                                      'open_status_names'],
                                  closed_status_names=tracker_json[
                                      'closed_status_names'],
                                  **tracker_json['tracker_config']['options']
                                  )
        ThreadLocalORMSession.flush_all()
        try:
            M.session.artifact_orm_session._get().skip_mod_date = True
            for ticket_json in tracker_json['tickets']:
                reporter = self.get_user(ticket_json['reported_by'])
                owner = self.get_user(ticket_json['assigned_to'])
                with h.push_config(c, user=reporter, app=app):
                    self.max_ticket_num = max(
                        ticket_json['ticket_num'], self.max_ticket_num)
                    ticket = TM.Ticket(
                        app_config_id=app.config._id,
                        import_id=import_id_converter.expand(
                            ticket_json['ticket_num'], app),
                        description=self.annotate(
                            self.annotate(
                                ticket_json['description'],
                                owner, ticket_json[
                                    'assigned_to'], label=' owned'),
                            reporter, ticket_json[
                                'reported_by'], label=' created'),
                        created_date=dateutil.parser.parse(
                            ticket_json['created_date']),
                        mod_date=dateutil.parser.parse(
                            ticket_json['mod_date']),
                        ticket_num=ticket_json['ticket_num'],
                        summary=ticket_json['summary'],
                        custom_fields=ticket_json['custom_fields'],
                        status=ticket_json['status'],
                        labels=ticket_json['labels'],
                        votes_down=ticket_json['votes_down'],
                        votes_up=ticket_json['votes_up'],
                        votes=ticket_json['votes_up'] -
                        ticket_json['votes_down'],
                        assigned_to_id=owner._id,
                    )
                    # add an attachment to the ticket
                    ticket.add_multiple_attachments([File(a['url'])
                                                    for a in ticket_json['attachments']])
                    # trigger the private property
                    ticket.private = ticket_json['private']
                    self.process_comments(
                        ticket, ticket_json['discussion_thread']['posts'])
                    session(ticket).flush(ticket)
                    session(ticket).expunge(ticket)
            app.globals.custom_fields = tracker_json['custom_fields']
            self.process_bins(app, tracker_json['saved_bins'])
            app.globals.last_ticket_num = self.max_ticket_num
            M.AuditLog.log(
                'import tool {} from exported Allura JSON'.format(
                    app.config.options.mount_point,
                ),
                project=project,
                user=user,
                url=app.url,
            )
            g.post_event('project_updated')
            app.globals.invalidate_bin_counts()
            ThreadLocalORMSession.flush_all()
            return app
        except Exception:
            h.make_app_admin_only(app)
            raise
        finally:
            M.session.artifact_orm_session._get().skip_mod_date = False

    def process_comments(self, ticket, comments):
        for comment_json in comments:
            user = self.get_user(comment_json['author'])
            with h.push_config(c, user=user):
                p = ticket.discussion_thread.add_post(
                    text=self.annotate(
                        comment_json[
                            'text'], user, comment_json['author']),
                    ignore_security=True,
                    timestamp=dateutil.parser.parse(
                        comment_json['timestamp']),
                )
                p.add_multiple_attachments([File(a['url'])
                                           for a in comment_json['attachments']])

    def process_bins(self, app, bins):
        TM.Bin.query.remove({'app_config_id': app.config._id})
        for bin_json in bins:
            bin_json.pop('_id', None)
            TM.Bin(app_config_id=app.config._id, **bin_json)
