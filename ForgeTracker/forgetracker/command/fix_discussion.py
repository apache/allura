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

from bson import ObjectId
from bson.errors import InvalidId
from ming.orm import ThreadLocalORMSession
from tg import tmpl_context as c

from allura.command import base
from allura import model as M
from allura.lib import exceptions as exc
from forgetracker.model import Ticket


class FixDiscussion(base.Command):

    """Fixes trackers that had used buggy 'ticket move' feature before it was fixed.

    See [#5727] for details.

    Usage:

    paster fix-discussion ../Allura/development.ini [project_name_or_id]

    If used with optional parameter will fix trackers for specified project,
    else will fix all trackers in all projects.
    """
    group_name = 'ForgeTracker'
    min_args = 1
    max_args = 2
    usage = '<ini file> [project_name_or_id]'
    summary = "Fix trackers that had used buggy 'ticket move' feature"
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()

        if len(self.args) >= 2:
            p_name_or_id = self.args[1]
            try:
                project = M.Project.query.get(_id=ObjectId(p_name_or_id))
            except InvalidId:
                projects = M.Project.query.find({'$or': [
                    {'shortname': p_name_or_id},
                    {'name': p_name_or_id}
                ]})
                if projects.count() > 1:
                    raise exc.ForgeError('Multiple projects has a shortname %s. '
                                         'Use project _id instead.' % p_name_or_id)
                project = projects.first()
            if not project:
                raise exc.NoSuchProjectError('The project %s '
                                             'could not be found' % p_name_or_id)

            self.fix_for_project(project)
        else:
            base.log.info(
                'Checking discussion instances for each tracker in all projects')
            for project in M.Project.query.find():
                self.fix_for_project(project)

    def fix_for_project(self, project):
        c.project = project
        base.log.info(
            'Checking discussion instances for each tracker in project %s' %
            project.shortname)
        trackers = [ac for ac in project.app_configs
                    if ac.tool_name.lower() == 'tickets']
        for tracker in trackers:
            base.log.info('Found tracker %s' % tracker)
            for ticket in Ticket.query.find({'app_config_id': tracker._id}):
                base.log.info('Processing ticket %s [#%s] %s'
                              % (ticket._id, ticket.ticket_num, ticket.summary))
                if ticket.discussion_thread.discussion.app_config_id != tracker._id:
                    # Some tickets were moved from this tracker,
                    # and Discussion instance for entire tracker was moved too.
                    # Should move it back.
                    base.log.info("Some tickets were moved from this tracker. "
                                  "Moving tracker's discussion instance back.")
                    ticket.discussion_thread.discussion.app_config_id = tracker._id

                if ticket.discussion_thread.discussion_id != tracker.discussion_id:
                    # Ticket was moved from another tracker.
                    # Should bind his comment thread to tracker's Discussion
                    base.log.info("Ticket was moved from another tracker. "
                                  "Bind ticket's comment thread to tracker's Discussion instance.")
                    ticket.discussion_thread.discussion_id = tracker.discussion_id
                    for post in ticket.discussion_thread.posts:
                        post.discussion_id = tracker.discussion_id

            ThreadLocalORMSession.flush_all()
