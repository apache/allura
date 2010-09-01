import sys
import json
import logging

from pylons import c

from ming.orm import session, MappedClass

from allura import model as M
from forgetracker import model as TM

log = logging.getLogger(__name__)

def main():
    test = sys.argv[-1] == 'test'
    projects = M.Project.query.find().all()
    log.info('Fixing tracker fields')
    for p in projects:
        if p.parent_id: continue
        c.project = p
        q = TM.Globals.query.find()
        if not q.count(): continue
        for g in q:
            if g.open_status_names: continue
            if g.status_names is None: old_names = ['open', 'closed']
            else: old_names = g.status_names.split() or ['open', 'closed']
            if g.open_status_names is None:
                g.open_status_names = ' '.join(
                    name for name in old_names if name != 'closed')
            if g.closed_status_names is None:
                g.closed_status_names = 'closed'
        if test:
            log.info('... would fix tracker(s) in %s', p.shortname)
        else:
            log.info('... fixing tracker(s) in %s', p.shortname)
            session(g).flush()
        session(g).clear()

if __name__ == '__main__':
    main()
