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

import sys
import logging

from pylons import tmpl_context as c

from ming.orm import session

from allura import model as M
from forgetracker import model as TM

log = logging.getLogger(__name__)


def main():
    test = sys.argv[-1] == 'test'
    all_projects = M.Project.query.find().all()
    log.info('Fixing tracker thread subjects')
    for project in all_projects:
        if project.parent_id:
            continue
        c.project = project
        # will find all tickets for all trackers in this project
        all_tickets = TM.Ticket.query.find()
        if not all_tickets.count():
            continue
        for ticket in all_tickets:
            thread = ticket.get_discussion_thread()
            thread.subject = ''
        if test:
            log.info('... would fix ticket threads in %s', project.shortname)
        else:
            log.info('... fixing ticket threads in %s', project.shortname)
            session(project).flush()
        session(project).clear()

if __name__ == '__main__':
    main()
