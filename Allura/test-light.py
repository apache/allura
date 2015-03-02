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

from pylons import tmpl_context as c

from allura.lib import helpers as h
from allura.model.repository import CommitDoc, TreeDoc, TreesDoc
from allura.model.repository import LastCommitDoc, CommitRunDoc
from allura.model.repo_refresh import refresh_repo


def main():
    if len(sys.argv) > 1:
        h.set_context('test')
        c.project.install_app('Git', 'code', 'Code',
                              init_from_url='/home/rick446/src/forge')
        c.project.install_app('Hg', 'code2', 'Code2',
                              init_from_url='/home/rick446/src/Kajiki')
    CommitDoc.m.remove({})
    TreeDoc.m.remove({})
    TreesDoc.m.remove({})
    LastCommitDoc.m.remove({})
    CommitRunDoc.m.remove({})

    h.set_context('test', 'code')
    refresh_repo(c.app.repo, notify=False)
    h.set_context('test', 'code2')
    refresh_repo(c.app.repo, notify=False)


if __name__ == '__main__':
    main()
    # dolog()
