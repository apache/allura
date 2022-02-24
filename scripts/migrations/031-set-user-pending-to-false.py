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

from ming.odm import ThreadLocalORMSession, state

from allura.lib import utils
from allura import model as M

log = logging.getLogger(__name__)


def main():
    for chunk in utils.chunked_find(M.User):
        for user in chunk:
            print(f'Processing {user.username}')
            user.pending = False
            # Ming doesn't mark document for update, since pending is False
            # by default, even if field is missing from mongo
            state(user).status = state(user).dirty
            ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
