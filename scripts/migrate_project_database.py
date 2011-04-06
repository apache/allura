import os
import sys
import shutil
import logging

from pylons import c
from ming.orm import session
from allura import model as M
log = logging.getLogger(__name__)

MONGO_HOME=os.environ.get('MONGO_HOME', '/usr')
MONGO_DUMP=os.path.join(MONGO_HOME, 'bin/mongodump')
MONGO_RESTORE=os.path.join(MONGO_HOME, 'bin/mongorestore')
SHARD_LENGTH=1

def main():
    if len(sys.argv) > 1:
        shortnames = sys.argv[1:]
    else:
        shortnames = [ p.shortname for p in M.Project.query.find(dict(is_root=True)) ]
    M.main_orm_session.clear()
    for pname in shortnames:
        # This needs to be a .find() instead of a .get() because of the
        # __init__ projects, which have the same shortname but exist in
        # multiple neighborhoods.
        for project in M.Project.query.find(dict(shortname=pname)):
            migrate_project_database(project)

def migrate_project_database(project):
    c.project = project
    target_uri = M.Project.default_database_uri(project.shortname)
    target_db = target_uri.rsplit('/')[-1]
    if project is None:
        log.fatal('Project %s not found', project.shortname)
        return 2
    if project.database_uri == target_uri:
        log.info('Project %s is already migrated to %s', project.shortname, project.database_uri)
        return 2
    conn = M.session.main_doc_session.db.connection
    host = '%s:%s' % (conn.host, conn.port)
    dirname = os.tempnam()
    try:
        log.info('Backing up %s to %s', project.shortname, dirname)
        db_uri = project.database_uri
        db = db_uri.rsplit('/')[-1]
        assert 0 == os.system('%s --host %s --db %s -o %s' % (
                MONGO_DUMP, host, db, dirname))
        assert 0 == os.system('%s --host %s --db %s %s/%s ' % (
                MONGO_RESTORE, host, target_db, dirname, db))
        for p in M.Project.query.find(dict(database_uri=db_uri)):
            p.database_uri = M.Project.default_database_uri(project.shortname)
        session(project).flush()
        conn.drop_database(db)
    finally:
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
    return 0

def pm(etype, value, tb): # pragma no cover
    import pdb, traceback
    try:
        from IPython.ipapi import make_session; make_session()
        from IPython.Debugger import Pdb
        sys.stderr.write('Entering post-mortem IPDB shell\n')
        p = Pdb(color_scheme='Linux')
        p.reset()
        p.setup(None, tb)
        p.print_stack_trace()
        sys.stderr.write('%s: %s\n' % ( etype, value))
        p.cmdloop()
        p.forget()
        # p.interaction(None, tb)
    except ImportError:
        sys.stderr.write('Entering post-mortem PDB shell\n')
        traceback.print_exception(etype, value, tb)
        pdb.post_mortem(tb)

sys.excepthook = pm

if __name__ == '__main__':
    sys.exit(main())
