import sys
import logging
from contextlib import contextmanager

from pylons import g

from allura.lib.decorators import task
from allura.lib.exceptions import CompoundError

log = logging.getLogger(__name__)

@task
def add_artifacts(ref_ids, update_solr=True, update_refs=True):
    '''Add the referenced artifacts to SOLR and shortlinks'''
    from allura import model as M
    from allura.lib.search import find_shortlinks, solarize
    exceptions = []
    solr_updates = []
    with _indexing_disabled(M.session.artifact_orm_session._get()):
        for ref in M.ArtifactReference.query.find(dict(_id={'$in': ref_ids})):
            try:
                artifact = ref.artifact
                s = solarize(artifact)
                if s is None:
                    continue
                if update_solr:
                    solr_updates.append(s)
                if update_refs:
                    if isinstance(artifact, M.Snapshot):
                        continue
                    ref.references = [
                        link.ref_id for link in find_shortlinks(s['text']) ]
            except Exception:
                log.error('Error indexing artifact %s', ref._id)
                exceptions.append(sys.exc_info())
        g.solr.add(solr_updates)

    if len(exceptions) == 1:
        raise exceptions[0][0], exceptions[0][1], exceptions[0][2]
    if exceptions:
        raise CompoundError(*exceptions)

@task
def del_artifacts(ref_ids):
    from allura import model as M
    if not ref_ids: return
    solr_query = 'id:({0})'.format(' || '.join(ref_ids))
    g.solr.delete(q=solr_query)
    M.ArtifactReference.query.remove(dict(_id={'$in':ref_ids}))
    M.Shortlink.query.remove(dict(ref_id={'$in':ref_ids}))

@task
def commit():
    g.solr.commit()

@contextmanager
def _indexing_disabled(session):
    session.disable_artifact_index = session.skip_mod_date = True
    try:
        yield session
    finally:
        session.disable_artifact_index = session.skip_mod_date = False
