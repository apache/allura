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

from ming.orm import ThreadLocalORMSession
from allura import model as M
from forgetracker import model as TM
from forgewiki import model as WM
from forgediscussion import model as DM

log = logging.getLogger(__name__)


def main():
    db = M.project_doc_session.db
    log.info('=== Making attachments in %s polymorphic ===', db)
    log.info('Fixing %d discussions', M.Discussion.query.find().count())
    for d in M.Discussion.query.find():
        for a in M.DiscussionAttachment.query.find(dict(
                discussion_id=d._id)):
            log.info('%s: %s', d.url(), a.filename)
    log.info('Fixing %d forums', DM.Forum.query.find().count())
    for d in DM.Forum.query.find():
        for a in DM.ForumAttachment.query.find(dict(
                discussion_id=d._id)):
            log.info('%s: %s', d.url(), a.filename)
    log.info('Fixing %d tickets', TM.Ticket.query.find().count())
    for t in TM.Ticket.query.find():
        for a in TM.TicketAttachment.query.find(dict(
                artifact_id=t._id)):
            log.info('%s: %s', t.url(), a.filename)
    log.info('Fixing %d wikis', WM.Page.query.find().count())
    for p in WM.Page.query.find():
        for a in WM.WikiAttachment.query.find(dict(
                artifact_id=p._id)):
            log.info('%s: %s', p.url(), a.filename)
    ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
