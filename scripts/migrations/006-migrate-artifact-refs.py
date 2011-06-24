import sys
import logging
from cPickle import loads

from pylons import c

from allura import model as M

log = logging.getLogger('allura.migrate-artifact-refs')

# Threads have artifact references that must be migrated to the new system
def main():
    test = sys.argv[-1] == 'test'
    all_projects = M.Project.query.find().all()
    log.info('Fixing artifact references in threads')
    seen_dbs = set()
    for project in all_projects:
        if project.database_uri in seen_dbs: continue
        seen_dbs.add(project.database_uri)
        c.project = project
        db = M.project_doc_session.db
        for thread in db.thread.find():
            ref = thread.pop('artifact_reference', None)
            if ref is None: continue
            Artifact = loads(ref['artifact_type'])
            artifact = Artifact.query.get(_id=ref['artifact_id'])
            M.ArtifactReference.from_artifact(artifact)
            thread['ref_id'] = artifact.index_id()
            if not test:
                db.thread.save(thread)
                log.info('saving thread %s', thread['_id'])
            else:
                log.info('would save thread %s', thread['_id'])
            M.artifact_orm_session.clear()

if __name__ == '__main__':
    main()
