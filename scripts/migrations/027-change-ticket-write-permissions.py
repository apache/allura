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

from allura import model as M

from allura.lib import utils

log = logging.getLogger(__name__)


def add(acl, role):
    if role not in acl:
        acl.append(role)

# migration script for change write permission to create + update


def main():
    query = {'tool_name': {'$regex': '^tickets$', '$options': 'i'}}
    for chunk in utils.chunked_find(M.AppConfig, query):
        for a in chunk:
            # change 'deny write' and 'write' permission
            role_ids = [(p.role_id, p.access)
                        for p in a.acl if p.permission == 'write']
            for role_id, access in role_ids:
                if access == M.ACE.DENY:
                    add(a.acl, M.ACE.deny(role_id, 'create'))
                    add(a.acl, M.ACE.deny(role_id, 'update'))
                else:
                    add(a.acl, M.ACE.allow(role_id, 'create'))
                    add(a.acl, M.ACE.allow(role_id, 'update'))

        ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
