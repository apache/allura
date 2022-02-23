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

import logging
from datetime import datetime

from tg import tmpl_context as c

from allura.lib.decorators import task
from allura.lib import helpers as h
from allura import model as M

log = logging.getLogger(__name__)


@task
def update_bin_counts(app_config_id):
    app_config = M.AppConfig.query.get(_id=app_config_id)
    app = app_config.project.app_instance(app_config)
    with h.push_config(c, app=app):
        app.globals.update_bin_counts()


@task
def move_tickets(ticket_ids, destination_tracker_id):
    c.app.globals.move_tickets(ticket_ids, destination_tracker_id)


@task
def bulk_edit(**post_data):
    try:
        M.artifact_orm_session._get().skip_last_updated = True
        c.app.globals.update_tickets(**post_data)
        # manually update project's last_updated field at the end of the
        # import instead of it being updated automatically by each artifact
        # since long-running task can cause stale project data to be saved
        M.Project.query.update(
            {'_id': c.project._id},
            {'$set': {'last_updated': datetime.utcnow()}})
    finally:
        M.artifact_orm_session._get().skip_last_updated = False
