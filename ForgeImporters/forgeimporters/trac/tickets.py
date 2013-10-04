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

from formencode import validators as fev

from ming.orm import session
from pylons import tmpl_context as c
from pylons import app_globals as g
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
from allura.lib.decorators import require_post, task
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
        ImportErrorHandler,
        )
from forgetracker.tracker_main import ForgeTrackerApp
from forgetracker.import_support import ImportSupport


@task(notifications_disabled=True)
def import_tool(**kw):
    importer = TracTicketImporter()
    with ImportErrorHandler(importer, kw.get('trac_url'), c.project):
        importer.import_tool(c.project, c.user, **kw)


class TracTicketImportForm(ToolImportForm):
    trac_url = fev.URL(not_empty=True)
    user_map = v.UserMapJsonFile(as_string=True)


class TracTicketImportController(BaseController):
    def __init__(self):
        self.importer = TracTicketImporter()
        self.task = import_tool

    @property
    def target_app(self):
        return self.importer.target_app

    @with_trailing_slash
    @expose('jinja:forgeimporters.trac:templates/tickets/index.html')
    def index(self, **kw):
        return dict(importer=self.importer,
                target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(TracTicketImportForm(ForgeTrackerApp), error_handler=index)
    def create(self, trac_url, mount_point, mount_label, user_map=None, **kw):
        if self.importer.enforce_limit(c.project):
            self.task.post(
                    mount_point=mount_point,
                    mount_label=mount_label,
                    trac_url=trac_url,
                    user_map=user_map)
            flash('Ticket import has begun. Your new tracker will be available '
                    'when the import is complete.')
        else:
            flash('There are too many imports pending at this time.  Please wait and try again.', 'error')
        redirect(c.project.url() + 'admin/')


class TracTicketImporter(ToolImporter):
    target_app = ForgeTrackerApp
    source = 'Trac'
    controller = TracTicketImportController
    tool_label = 'Tickets'
    tool_description = 'Import your tickets from Trac'

    def import_tool(self, project, user, project_name=None, mount_point=None,
            mount_label=None, trac_url=None, user_map=None, **kw):
        """ Import Trac tickets into a new Allura Tracker tool.

        """
        trac_url = trac_url.rstrip('/') + '/'
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
                ImportSupport().perform_import(
                        json.dumps(export(trac_url), cls=DateJSONEncoder),
                        json.dumps({
                            'user_map': json.loads(user_map) if user_map else {},
                            'usernames_match': self.usernames_match(trac_url),
                            }),
                        )
            AuditLog.log(
                'import tool %s from %s' % (
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
