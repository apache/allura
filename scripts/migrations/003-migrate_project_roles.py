'''Merge all the OldProjectRole collections in various project databases into a
central ProjectRole collection.
'''
import logging

from pylons import c

from ming.orm import session, state
from allura import model as M

log = logging.getLogger(__name__)

seen_databases = set()
projects = M.Project.query.find().all()

for p in projects:
    if p.database_uri in seen_databases:
        continue
    seen_databases.add(p.database_uri)
    log.info('Moving project roles in database %s to main DB',
             p.database_uri)
    c.project = p
    for opr in M.OldProjectRole.query.find():
        pr = M.ProjectRole(**state(opr).document)
    session(opr).clear()
    session(pr).flush()
    session(pr).clear()
