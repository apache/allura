import os
import logging
from contextlib import contextmanager

from pylons import g

from allura.lib.decorators import task

log = logging.getLogger(__name__)

@task
def index():
    from allura import model as M
    '''index all the artifacts that have changed since the last index() call'''
    worker = '%s pid %s' % (os.uname()[1], os.getpid())
    with _indexing_disabled(M.session.artifact_orm_session._get()):
        M.IndexOp.lock_ops(worker)
        for i, op in enumerate(M.IndexOp.find_ops(worker)):
            op()
        log.info('Executed %d index ops', i)
        if i: g.solr.commit()
        M.IndexOp.remove_ops(worker)

def sinfo(s):
    return 'DIA,SMD=%s,%s' % (
        s.disable_artifact_index,
        s.skip_mod_date)

@contextmanager
def _indexing_disabled(session):
    session.disable_artifact_index = session.skip_mod_date = True
    try:
        yield session
    finally:
        session.disable_artifact_index = session.skip_mod_date = False
