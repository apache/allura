import os
import sys
import json
import logging

from ming.orm import state, session
from ming.orm.base import instrument, DocumentTracker

from pymongo.json_util import default, object_hook
from allura import model as M
from allura.command import ReindexCommand

log = logging.getLogger(__name__)

MONGO_HOME=os.environ.get('MONGO_HOME', '')
MONGO_DUMP=os.path.join(MONGO_HOME, 'bin/mongodump')
MONGO_RESTORE=os.path.join(MONGO_HOME, 'bin/mongorestore')

def main():
    if len(sys.argv) != 3:
        log.error('Usage: %s <dirname> <new_shortname>', sys.argv[0])
        return
    dirname = sys.argv[1]
    new_pname = sys.argv[2]
    restore_project(dirname, new_pname)

def restore_project(dirname, new_shortname=None):
    log.info('Reloading %s into %s', dirname, new_shortname)
    with open(os.path.join(dirname, 'project.json')) as fp:
        project_doc = json.load(fp, object_hook=object_hook)
    project = M.Project.query.get(_id=project_doc['_id'])
    st = state(project)
    st.document = instrument(project_doc, DocumentTracker(st))
    if project is None:
        log.fatal('Project not found')
        return
    dump_path = os.path.join(dirname, project.database)
    with open(os.path.join(dirname, 'project.json')) as fp:
        project_doc = json.load(fp, object_hook=object_hook)
    st = state(project)
    st.document = instrument(project_doc, DocumentTracker(st))
    project.shortname = new_shortname
    project.database = 'project:' + new_shortname.replace('/', ':').replace('-', '_')
    project.deleted = False
    conn = M.main_doc_session.bind.conn
    if project.database in conn.database_names():
        raw_input('''Warning: database %s is already populated.  If you do NOT want
    to drop the database and create a new one, press Crtl-C NOW!  Otherwise,
    press enter to continue.''' % project.database)
        conn.drop_database(project.database)
    os.system('%s --db %s %s' % (
            MONGO_RESTORE, project.database, dump_path))
    session(project).flush()
    reindex= ReindexCommand('reindex')
    reindex.run(['--project', new_shortname])

if __name__ == '__main__':
    main()
