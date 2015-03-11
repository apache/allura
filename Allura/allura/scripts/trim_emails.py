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

from allura.scripts import ScriptTask
from allura import model as M
from allura.lib.utils import chunked_find


log = logging.getLogger(__name__)


class TrimEmails(ScriptTask):

    @classmethod
    def execute(cls, options):
        for chunk in chunked_find(M.User, {}):
            for u in chunk:
                log.info('Trimming emails for user %s', u.username)
                new_addresses = [M.EmailAddress.canonical(addr) for addr in u.email_addresses]
                u.email_addresses = new_addresses
                if u.preferences.email_address is not None:
                    u.preferences.email_address = M.EmailAddress.canonical(
                        u.preferences.email_address)
        log.info('Finished trimming emails')


if __name__ == '__main__':
    TrimEmails.main()
