import os
import logging

from pylons import g

from allura import model as M
from allura.lib.utils import task

log = logging.getLogger(__name__)

@task
def index():
    '''index all the artifacts that have changed since the last index() call'''
    worker = '%s pid %s' % (os.uname()[1], os.getpid())
    M.IndexOp.lock_ops(worker)
    for i, op in enumerate(M.IndexOp.find_ops(worker)):
        op()
    log.info('Executed %d index ops', i)
    if i: g.solr.commit()
    M.IndexOp.remove_ops(worker)
