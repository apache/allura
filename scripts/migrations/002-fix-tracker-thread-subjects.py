import sys
import logging

from pylons import c

from ming.orm import session

from allura import model as M
from forgetracker import model as TM

log = logging.getLogger(__name__)

def main():
    test = sys.argv[-1] == 'test'
    all_projects = M.Project.query.find().all()
    log.info('Fixing tracker thread subjects')
    for project in all_projects:
        if project.parent_id: continue
        c.project = project
        all_tickets = TM.Ticket.query.find() # will find all tickets for all trackers in this project
        if not all_tickets.count(): continue
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
