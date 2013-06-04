#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import sys
import logging
from contextlib import contextmanager

from pylons import app_globals as g

from allura.lib.decorators import task
from allura.lib.exceptions import CompoundError
from allura.lib.solr import make_solr_from_config

log = logging.getLogger(__name__)

@task
def add_artifacts(ref_ids, update_solr=True, update_refs=True, solr_hosts=None):
    '''
    Add the referenced artifacts to SOLR and shortlinks.

    :param solr_hosts: a list of solr hosts to use instead of the defaults
    :type solr_hosts: [str]
    '''
    from allura import model as M
    from allura.lib.search import find_shortlinks, solarize
    if solr_hosts:
        solr = make_solr_from_config(solr_hosts)
    else:
        solr = g.solr
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
        solr.add(solr_updates)

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
