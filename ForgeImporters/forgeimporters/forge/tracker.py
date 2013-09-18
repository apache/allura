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

import os
from collections import defaultdict
from datetime import datetime
import json

import dateutil.parser
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
from allura.lib.decorators import require_post, task
from allura.lib import validators as v
from allura import model as M

from forgetracker.tracker_main import ForgeTrackerApp
from forgetracker import model as TM
from forgeimporters.base import (
        ToolImporter,
        ToolImportForm,
        ImportErrorHandler,
        File,
        get_importer_upload_path,
        save_importer_upload,
        )


@task(notifications_disabled=True)
def import_tool(**kw):
    importer = ForgeTrackerImporter()
    with ImportErrorHandler(importer, kw.get('project_name'), c.project):
        importer.import_tool(c.project, c.user, **kw)


class ForgeTrackerImportForm(ToolImportForm):
    tickets_json = v.JsonFile(required=True)


class ForgeTrackerImportController(BaseController):
    def __init__(self):
        self.importer = ForgeTrackerImporter()

    @property
    def target_app(self):
        return self.importer.target_app

    @with_trailing_slash
    @expose('jinja:forgeimporters.forge:templates/tracker/index.html')
    def index(self, **kw):
        return dict(importer=self.importer,
                target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(ForgeTrackerImportForm(ForgeTrackerApp), error_handler=index)
    def create(self, tickets_json, mount_point, mount_label, **kw):
        if ForgeTrackerImporter().enforce_limit(c.project):
            save_importer_upload(c.project, 'tickets.json', json.dumps(tickets_json))
            import_tool.post(
                    mount_point=mount_point,
                    mount_label=mount_label,
                )
            flash('Ticket import has begun. Your new tracker will be available '
                    'when the import is complete.')
            redirect(c.project.url() + 'admin/')
        else:
            flash('There are too many imports pending at this time.  Please wait and try again.', 'error')
        redirect(c.project.url() + 'admin/')


class ForgeTrackerImporter(ToolImporter):
    source = 'Allura'
    target_app = ForgeTrackerApp
    controller = ForgeTrackerImportController
    tool_label = 'Tickets'

    def __init__(self, *args, **kwargs):
        super(ForgeTrackerImporter, self).__init__(*args, **kwargs)
        self.max_ticket_num = 0

    def _load_json(self, project):
        upload_path = get_importer_upload_path(project)
        full_path = os.path.join(upload_path, 'tickets.json')
        with open(full_path) as fp:
            return json.load(fp)

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
                open_status_names=tracker_json['open_status_names'],
                closed_status_names=tracker_json['closed_status_names'],
                **tracker_json['tracker_config']['options']
            )
        ThreadLocalORMSession.flush_all()
        try:
            M.session.artifact_orm_session._get().skip_mod_date = True
            for ticket_json in tracker_json['tickets']:
                reporter = self.get_user(ticket_json['reported_by'])
                with h.push_config(c, user=reporter, app=app):
                    self.max_ticket_num = max(ticket_json['ticket_num'], self.max_ticket_num)
                    ticket = TM.Ticket(
                            app_config_id=app.config._id,
                            import_id=import_id_converter.expand(ticket_json['ticket_num'], app),
                            description=self.annotate(ticket_json['description'], reporter, ticket_json['reported_by']),
                            created_date=dateutil.parser.parse(ticket_json['created_date']),
                            mod_date=dateutil.parser.parse(ticket_json['mod_date']),
                            ticket_num=ticket_json['ticket_num'],
                            summary=ticket_json['summary'],
                            custom_fields=ticket_json['custom_fields'],
                            status=ticket_json['status'],
                            labels=ticket_json['labels'],
                            votes_down=ticket_json['votes_down'],
                            votes_up=ticket_json['votes_up'],
                            votes = ticket_json['votes_up'] - ticket_json['votes_down'],
                        )
                    ticket.private = ticket_json['private']  # trigger the private property
                    self.process_comments(ticket, ticket_json['discussion_thread']['posts'])
                    session(ticket).flush(ticket)
                    session(ticket).expunge(ticket)
            app.globals.custom_fields = tracker_json['custom_fields']
            self.process_bins(app, tracker_json['saved_bins'])
            app.globals.last_ticket_num = self.max_ticket_num
            M.AuditLog.log(
                    'import tool %s from exported Allura JSON' % (
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
        except Exception as e:
            h.make_app_admin_only(app)
            raise
        finally:
            M.session.artifact_orm_session._get().skip_mod_date = False

    def get_user(self, username):
        user = M.User.by_username(username)
        if not user:
            user = M.User.anonymous()
        return user

    def annotate(self, text, user, username):
        if user._id is None:
            return '*Originally by:* %s\n\n%s' % (username, text)
        return text

    def process_comments(self, ticket, comments):
        for comment_json in comments:
            user = self.get_user(comment_json['author'])
            with h.push_config(c, user=user):
                p = ticket.discussion_thread.add_post(
                        text = self.annotate(comment_json['text'], user, comment_json['author']),
                        ignore_security = True,
                        timestamp = dateutil.parser.parse(comment_json['timestamp']),
                    )
                p.add_multiple_attachments([File(a['url']) for a in comment_json['attachments']])

    def process_bins(self, app, bins):
        TM.Bin.query.remove({'app_config_id': app.config._id})
        for bin_json in bins:
            bin_json.pop('_id', None)
            TM.Bin(app_config_id=app.config._id, **bin_json)
