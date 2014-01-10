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

from ming.orm import session

from allura import model as M

log = logging.getLogger(__name__)

IGNORED_COLLECTIONS = [
    '_flyway_migration_info',
    'user',
    'config',
    'system.indexes']


def main():
    conn = M.session.main_doc_session.bind.conn
    n = M.Neighborhood.query.get(url_prefix='/u/')
    for p in M.Project.query.find(dict(neighborhood_id=n._id)):
        if not p.database_configured:
            continue
        if not p.shortname.startswith('u/'):
            continue
        log.info('Checking to see if %s is configured...', p.database)
        db = conn[p.database]
        if is_unconfigured(db):
            if sys.argv[-1] == 'test':
                log.info('... it is not, so I would drop it.')
                continue
            log.info('... it is not, so dropping it.')
            conn.drop_database(p.database)
            p.database_configured = False
            session(p).flush()
        else:
            log.info('... it is.')


def is_unconfigured(db):
    # Check for data in collections other than those we pre-fill with data
    for collection_name in db.collection_names():
        if collection_name in IGNORED_COLLECTIONS:
            continue
        collection = db[collection_name]
        if collection.count():
            log.info('...%s has data', collection_name)
            return False
    # DB is configured if it has more than profile/admin/search tools installed
    if db.config.count() != 3:
        log.info('...has %d tools', db.config.count())
        return False
    return True

if __name__ == '__main__':
    main()
