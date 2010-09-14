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

MONGO_HOME=os.environ.get('MONGO_HOME', '/usr')
MONGO_DUMP=os.path.join(MONGO_HOME, 'bin/mongodump')
MONGO_RESTORE=os.path.join(MONGO_HOME, 'bin/mongorestore')

def main():
    if len(sys.argv) != 4:
        log.error('Usage: %s <dirname> <new_shortname> <new_unix_group_name>', sys.argv[0])
        return 2
    dirname = sys.argv[1]
    new_pname = sys.argv[2]
    new_ug_name = sys.argv[3]
    return restore_project(dirname, new_pname, new_ug_name)

def restore_project(dirname, new_shortname, new_unix_group_name):
    log.info('Reloading %s into %s', dirname, new_shortname)
    with open(os.path.join(dirname, 'project.json')) as fp:
        project_doc = json.load(fp, object_hook=object_hook)
    project = M.Project.query.get(_id=project_doc['_id'])
    st = state(project)
    st.document = instrument(project_doc, DocumentTracker(st))
    if project is None:
        log.fatal('Project not found')
        return 2
    dump_path = os.path.join(dirname, project.database)
    with open(os.path.join(dirname, 'project.json')) as fp:
        project_doc = json.load(fp, object_hook=object_hook)
    st = state(project)
    st.document = instrument(project_doc, DocumentTracker(st))
    project.shortname = new_shortname
    project.set_tool_data('sfx', unix_group_name=new_unix_group_name)
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
    return 0

if __name__ == '__main__':
    sys.exit(main())
