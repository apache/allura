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

import logging

from ming.orm import ThreadLocalORMSession

from allura.lib import utils
from allura import model as M
from forgesvn import model as SM

log = logging.getLogger(__name__)


def kill_tree(repo, commit_id, path, tree):
    '''They were arboring terrorists, I swear.'''
    M.repository.Tree.query.remove(dict(_id=tree._id))
    for tree_rec in tree.tree_ids:
        tid = repo._tree_oid(commit_id, path + '/' + tree_rec.name)
        child_tree = M.repository.Tree.query.get(_id=tid)
        if child_tree:
            print('  Found {}'.format((path + '/' + tree_rec.name).encode('utf8')))
            kill_tree(repo, commit_id, path + '/' + tree_rec.name, child_tree)
        else:
            print('  Missing {}'.format((path + '/' + tree_rec.name).encode('utf8')))


def main():
    for chunk in utils.chunked_find(SM.Repository):
        for r in chunk:
            print(f'Processing {r}')
            all_commit_ids = r._impl.all_commit_ids()
            if all_commit_ids:
                for commit in M.repository.Commit.query.find({'_id': {'$in': all_commit_ids}}):
                    if commit.tree_id and M.repository.Tree.query.get(_id=commit.tree_id):
                        kill_tree(r._impl, commit._id, '', commit.tree)
                ThreadLocalORMSession.flush_all()
                ThreadLocalORMSession.close_all()

if __name__ == '__main__':
    main()
