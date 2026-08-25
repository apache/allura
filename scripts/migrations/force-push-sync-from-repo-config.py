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

"""
One-time sync of Repository.force_push_allowed from each git repo's own config.

Repos predating the force-push toggle have no force_push_allowed recorded, while their
receive.denyNonFastForwards may already be true, false, or unset.  This reads each repo and
stores what it actually permits, so the admin UI and menu label agree with reality.

Reads git; writes only Mongo.  No repo's behaviour changes.

Documents are read raw (validate=False) with a narrow projection, so a record that fails schema
validation -- e.g. a legacy doc whose acl is not a list -- cannot stop the run, and no ODM
objects accumulate in memory.

    paster script /var/local/config/production.ini \
        ../scripts/migrations/force-push-sync-from-repo-config.py -- --dry-run
"""

import argparse
import logging
import os
import sys

from ming.base import Object
from ming.odm import mapper

from forgegit import model as GM
from forgegit.model.git_repo import GitImplementation

log = logging.getLogger(__name__)

PROJECTION = {'fs_path': 1, 'name': 1, 'force_push_allowed': 1}


def parse_options():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would change without writing to Mongo')
    parser.add_argument('--pagesize', type=int, default=1024,
                        help='documents per query (default 1024)')
    return parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])


def iter_repo_docs(pagesize):
    # paged by _id like chunked_find, but raw: no schema validation, no identity map
    collection = mapper(GM.Repository).collection
    last_id = None
    while True:
        spec = {'_id': {'$gt': last_id}} if last_id else {}
        page = list(collection.m.find(spec, projection=PROJECTION, validate=False,
                                      sort=[('_id', 1)], limit=pagesize))
        if not page:
            return
        yield from page
        last_id = page[-1]['_id']
        if len(page) < pagesize:
            return


def main():
    opts = parse_options()
    counts = dict(seen=0, changed=0, unreadable=0)
    for doc in iter_repo_docs(opts.pagesize):
        counts['seen'] += 1
        path = os.path.join(doc.get('fs_path') or '', doc.get('name') or '')
        stored = bool(doc.get('force_push_allowed'))
        on_disk = GitImplementation(Object(full_fs_path=path)).force_push_allowed_on_disk()
        if on_disk is None:
            counts['unreadable'] += 1
            log.warning('unreadable, leaving alone: %s (%s)', path, doc['_id'])
            continue
        if on_disk == stored:
            continue
        counts['changed'] += 1
        log.info('%s: force_push_allowed %s => %s', path, stored, on_disk)
        if not opts.dry_run:
            GM.Repository.query.update({'_id': doc['_id']},
                                       {'$set': {'force_push_allowed': on_disk}})
    log.info('%s %d git repos: %d updated, %d unreadable',
             'would update' if opts.dry_run else 'synced', counts['seen'],
             counts['changed'], counts['unreadable'])


if __name__ == '__main__':
    main()
