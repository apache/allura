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

import argparse
import logging

from pymongo.errors import InvalidDocument

from allura.scripts import ScriptTask
from allura import model as M
from allura.tasks.index_tasks import add_users
from allura.lib.utils import chunked_find, chunked_list
from allura.lib.exceptions import CompoundError


log = logging.getLogger(__name__)


class ReindexUsers(ScriptTask):

    @classmethod
    def execute(cls, options):
        for chunk in chunked_find(M.User, {}):
            user_ids = []
            for u in chunk:
                log.info('Reindex user %s', u.username)
                if options.dry_run:
                    continue
                user_ids.append(u._id)
            try:
                for chunk in chunked_list(user_ids, options.max_chunk):
                    if options.tasks:
                        cls._post_add_users(chunk)
                    else:
                        add_users(chunk)
            except CompoundError as err:
                log.exception('Error indexing users:\n%r', err)
                log.error('%s', err.format_error())
            M.main_orm_session.flush()
            M.main_orm_session.clear()
        log.info('Reindex %s', 'queued' if options.tasks else 'done')

    @classmethod
    def _post_add_users(cls, chunk):
        """
        Post task, recursively splitting and re-posting if the resulting
        mongo document is too large.
        """
        try:
            add_users.post(chunk)
        except InvalidDocument as e:
            # there are many types of InvalidDocument, only recurse if its
            # expected to help
            if e.args[0].startswith('BSON document too large'):
                cls._post_add_users(chunk[:len(chunk) // 2])
                cls._post_add_users(chunk[len(chunk) // 2:])
            else:
                raise

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(description='Reindex all users into Solr (for searching)')
        parser.add_argument('--dry-run', action='store_true', dest='dry_run',
                            default=False, help='Log names of projects that would be reindexed, '
                            'but do not perform the actual reindex.')
        parser.add_argument('--tasks', action='store_true', dest='tasks',
                            help='Run each individual index operation as a background task.')
        parser.add_argument(
            '--max-chunk', dest='max_chunk', type=int, default=100 * 1000,
            help='Max number of artifacts to index in one Solr update command')
        return parser


def get_parser():
    return ReindexUsers.parser()


if __name__ == '__main__':
    ReindexUsers.main()
