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
import re
import sys
from tg import tmpl_context as c
from bson import ObjectId

from ming.odm import session
from ming.orm import ThreadLocalORMSession

from allura import model as M
from forgetracker import model as TM

log = logging.getLogger(__name__)


def main():
    task = sys.argv[-1]
    c.project = None

    # Fix ticket artifcat titles
    title = re.compile('^Ticket [0-9]')
    subs_tickets = M.Mailbox.query.find(dict(artifact_title=title)).all()
    log.info('Found total %d old artifact titles (tickets).', len(subs_tickets))
    for sub in subs_tickets:
        if not sub.artifact_index_id:
            log.info('No artifact_index_id on %s', sub)
            continue
        ticket = TM.Ticket.query.get(_id=ObjectId(sub.artifact_index_id.split('#')[1]))
        if not ticket:
            log.info('Could not find ticket for %s', sub)
            continue
        new_title = 'Ticket #%d: %s' % (ticket.ticket_num, ticket.summary)
        log.info('"%s" --> "%s"', sub.artifact_title, new_title)
        if(task != 'diff'):
            sub.artifact_title = new_title
        session(sub).flush(sub)

    # Fix merge request artifact titles
    title = re.compile('^Merge request: ')
    subs_mrs = M.Mailbox.query.find(dict(artifact_title=title)).all()
    log.info('Found total %d old artifact titles (merge_requests).', len(subs_tickets))
    for sub in subs_mrs:
        if not sub.artifact_index_id:
            log.info('No artifact_index_id on %s', sub)
            continue
        merge_request = M.MergeRequest.query.get(_id=ObjectId(sub.artifact_index_id.split('#')[1]))
        if not merge_request:
            log.info('Could not find merge request for %s', sub)
            continue
        new_title = 'Merge Request #%d: %s' % (merge_request.request_number, merge_request.summary)
        log.info('"%s" --> "%s"', sub.artifact_title, new_title)
        if task != 'diff':
            sub.artifact_title = new_title
        session(sub).flush(sub)


if __name__ == '__main__':
    main()
