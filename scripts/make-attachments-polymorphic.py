import logging

from pylons import c

from ming.orm import ThreadLocalORMSession
from allura import model as M
from forgetracker import model as TM
from forgewiki import model as WM
from forgediscussion import model as DM

log = logging.getLogger(__name__)

def main():
    dbs = dict((p.database_uri, p) for p in M.Project.query.find())
    for db, p in sorted(dbs.items()):
        log.info('=== Making attachments in %s polymorphic ===', db)
        c.project = p
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
                log.info('%s: %s' % p.url(), a.filename)
        ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
