import os
import sys
import json
import logging

from pylons import g

from ming.orm import state, session

from pymongo.json_util import default
from allura import model as M

log = logging.getLogger(__name__)

MONGO_HOME=os.environ.get('MONGO_HOME', '/usr')
MONGO_DUMP=os.path.join(MONGO_HOME, 'bin/mongodump')
MONGO_RESTORE=os.path.join(MONGO_HOME, 'bin/mongorestore')

def main():
    if len(sys.argv) not in (2,3):
        log.error('Usage: %s <shortname> [<backup_dir>]', sys.argv[0])
        return 1
    pname = sys.argv[1]
    project = M.Project.query.get(shortname=pname)
    if project is None:
        log.fatal('Project %s not found', pname)
        print 'Project %s not found' % pname
        return 2
    if len(sys.argv) == 3:
        backup_dir = sys.argv[2]
    else:
        pname = project.shortname
        gid = project.tool_data.get('sfx', {}).get('group_id', project._id)
        dirname = '%s-%s.purge' % (pname, gid)
        backup_dir = os.path.join(
            os.getcwd(), dirname)
    log.info('Backing up %s to %s', pname, backup_dir)
    dump_project(project, backup_dir)
    return 0

def dump_project(project, dirname):
    os.system('%s --db %s -o %s' % (
            MONGO_DUMP, project.database, dirname))
    with open(os.path.join(dirname, 'project.json'), 'w') as fp:
        json.dump(state(project).document, fp, default=default)

if __name__ == '__main__':
    sys.exit(main())
