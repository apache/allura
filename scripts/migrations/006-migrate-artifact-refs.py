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
from cPickle import loads

from allura import model as M

log = logging.getLogger('allura.migrate-artifact-refs')

# Threads have artifact references that must be migrated to the new system


def main():
    test = sys.argv[-1] == 'test'
    log.info('Fixing artifact references in threads')
    db = M.project_doc_session.db
    for thread in db.thread.find():
        ref = thread.pop('artifact_reference', None)
        if ref is None:
            continue
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
