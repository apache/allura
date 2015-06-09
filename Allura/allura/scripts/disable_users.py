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
import sys

from ming.odm import session

from allura.lib.plugin import AuthenticationProvider
from allura.scripts import ScriptTask
from allura import model as M


log = logging.getLogger(__name__)


class DisableUsers(ScriptTask):

    @classmethod
    def execute(cls, options):
        if options.usernames == ['-']:
            usernames = [line.strip() for line in sys.stdin]
        else:
            usernames = options.usernames
        cls.disable_users(usernames)

    @classmethod
    def disable_users(cls, usernames):
        auth_provider = AuthenticationProvider.get(request=None)

        # would be nice to use the BatchIndexer extension around this but that only works for artifacts not users

        for username in usernames:
            user = M.User.query.get(username=username)
            if not user:
                log.info('Could not find user: %s', username)
            elif user.disabled:
                log.info('User is already disabled: %s', username)
                session(user).expunge(user)
            else:
                log.info('Disabling user: %s', username)
                auth_provider.disable_user(user)
                session(user).flush(user)

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(description='Disable listed users')
        parser.add_argument(
            '--usernames', dest='usernames', type=str, nargs='+', metavar='<username>', required=True,
            help='List of usernames, or "-" to read from stdin')
        return parser


if __name__ == '__main__':
    DisableUsers.main()
