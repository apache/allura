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

from datetime import (
        datetime,
        timedelta,
        )
import json

import formencode as fe
from formencode import validators as fev

from pylons import tmpl_context as c
from pylons import app_globals as g
from tg import (
        config,
        expose,
        redirect,
        validate,
        )
from tg.decorators import (
        with_trailing_slash,
        without_trailing_slash,
        )

from allura.controllers import BaseController
from allura.lib.decorators import require_post
from allura.lib.import_api import AlluraImportApiClient
from allura.model import ApiTicket
from allura.scripts.trac_export import (
        TracExport,
        DateJSONEncoder,
        )

from forgeimporters.base import ToolImporter
from forgetracker.tracker_main import ForgeTrackerApp
from forgetracker.script.import_tracker import import_tracker


class TracTicketImportSchema(fe.Schema):
    trac_url = fev.URL(not_empty=True)
    mount_point = fev.UnicodeString()
    mount_label = fev.UnicodeString()


class TracTicketImportController(BaseController):
    @with_trailing_slash
    @expose('jinja:forgeimporters.trac:templates/tickets/index.html')
    def index(self, **kw):
        return {}

    @without_trailing_slash
    @expose()
    @require_post()
    @validate(TracTicketImportSchema(), error_handler=index)
    def create(self, trac_url, mount_point, mount_label, **kw):
        app = TracTicketImporter.import_tool(c.project,
                mount_point=mount_point,
                mount_label=mount_label,
                trac_url=trac_url,
                user=c.user)
        redirect(app.url())


class TracTicketImporter(ToolImporter):
    target_app = ForgeTrackerApp
    source = 'Trac'
    controller = TracTicketImportController
    tool_label = 'Trac Ticket Importer'
    tool_description = 'Import your tickets from Trac'

    def import_tool(self, project=None, mount_point=None, mount_label=None,
            trac_url=None, user=None):
        """ Import Trac tickets into a new Allura Tracker tool.

        """
        mount_point = mount_point or 'tickets'
        app = project.install_app(
                'Tickets',
                mount_point=mount_point,
                mount_label=mount_label or 'Tickets',
                )
        export = TracExport(trac_url)
        export_string = json.dumps(export, cls=DateJSONEncoder)
        api_ticket = ApiTicket(user_id=user._id,
                capabilities={"import": ["Projects", project.shortname]},
                expires=datetime.utcnow() + timedelta(minutes=60))
        cli = AlluraImportApiClient(config['base_url'], api_ticket.api_key,
                api_ticket.secret_key, False)
        import_tracker(cli, project.shortname, mount_point, {},
                export_string, validate=False)
        g.post_event('project_updated')
        return app
