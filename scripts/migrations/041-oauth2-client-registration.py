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

"""Marks OAuth2 clients created by dynamic registration or a Client ID Metadata Document before
OAuth2ClientApp.registration existed. Those are the clients with no owning user.

Dry run by default; pass `apply` to write. Safe to run more than once.

    paster script production.ini ../scripts/migrations/041-oauth2-client-registration.py -- apply
"""

import logging
import re
import sys

from allura import model as M

log = logging.getLogger(__name__)


def main():
    apply = sys.argv[-1] == 'apply'
    coll = M.main_doc_session.db[M.OAuth2ClientApp.__mongometa__.name]
    unmarked = {'user_id': None, 'registration': None}
    url = re.compile('^https://')
    for registration, client_id in (('cimd', url), ('dcr', {'$not': url})):
        query = dict(unmarked, client_id=client_id)
        if apply:
            n = coll.update_many(query, {'$set': {'registration': registration}}).modified_count
        else:
            n = coll.count_documents(query)
        log.info('%s %d client(s) as %r', 'marked' if apply else 'would mark', n, registration)


if __name__ == '__main__':
    main()
