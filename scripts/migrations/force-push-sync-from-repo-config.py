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

    paster script /var/local/config/production.ini \
        ../scripts/migrations/force-push-sync-from-repo-config.py -- --dry-run
"""

import argparse
import logging
import sys

from ming.odm import ThreadLocalODMSession

from allura.lib.utils import chunked_find
from forgegit import model as GM

log = logging.getLogger(__name__)


def parse_options():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would change without writing to Mongo')
    return parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])


def main():
    opts = parse_options()
    counts = dict(seen=0, changed=0, unreadable=0)
    for chunk in chunked_find(GM.Repository):
        for repo in chunk:
            counts['seen'] += 1
            on_disk = repo._impl.force_push_allowed_on_disk()
            if on_disk is None:
                counts['unreadable'] += 1
                log.warning('unreadable, leaving alone: %s', repo.full_fs_path)
                continue
            if on_disk == repo.force_push_allowed:
                continue
            counts['changed'] += 1
            log.info('%s: force_push_allowed %s => %s',
                     repo.full_fs_path, repo.force_push_allowed, on_disk)
            if not opts.dry_run:
                # targeted $set, not a whole-document save: taskd and the web app write other
                # fields on this record and a full flush would put back our stale copy of them
                repo.query.update({'$set': {'force_push_allowed': on_disk}})
        # drop each chunk from the identity map, or memory grows for the whole run
        ThreadLocalODMSession.close_all()
    log.info('%s %d git repos: %d updated, %d unreadable',
             'would update' if opts.dry_run else 'synced', counts['seen'],
             counts['changed'], counts['unreadable'])


if __name__ == '__main__':
    main()
