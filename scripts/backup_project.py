import os
import sys
import json
import logging

from pylons import g

from ming.orm import state, session

from pymongo.json_util import default
from pyforge import model as M

log = logging.getLogger(__name__)

MONGO_HOME=os.environ.get('MONGO_HOME', '')
MONGO_DUMP=os.path.join(MONGO_HOME, 'bin/mongodump')
MONGO_RESTORE=os.path.join(MONGO_HOME, 'bin/mongorestore')

def main():
    if len(sys.argv) != 2:
        log.error('Usage: %s <shortname>', sys.argv[0])
        return
    pname = sys.argv[1]
    log.info('Backing up %s', pname)
    project = M.Project.query.get(shortname=pname)
    if project is None:
        log.fatal('Project %s not found', pname)
        return
    dump_project(project)

def dump_project(project):
    pname = project.shortname
    gid = project.tool_data.get('sfx', {}).get('group_id', project._id)
    dirname = '%s-%s.purge' % (pname, gid)
    log.info('Backup %s to %s', pname, dirname)
    os.system('%s --db %s -o %s' % (
            MONGO_DUMP, project.database, dirname))
    with open(os.path.join(dirname, 'project.json'), 'w') as fp:
        json.dump(state(project).document, fp, default=default)

if __name__ == '__main__':
    main()
