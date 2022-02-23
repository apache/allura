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

import argparse

from allura.model import main_orm_session, main_explicitflush_orm_session

from allura.scripts import ScriptTask
from allura import model as M
from allura.lib.plugin import AuthenticationProvider
from allura.lib.utils import chunked_find

log = logging.getLogger('allura.scripts.backfill_previous_login_details')


class BackfillPreviousLoginDetails(ScriptTask):

    @classmethod
    def parser(cls):
        return argparse.ArgumentParser(description="Backfill previous login details from audit logs.  "
                                                   "Needed if auth.hibp_failure_force_pwd_change is enabled")

    @classmethod
    def execute(cls, options):
        auth_provider = AuthenticationProvider.get(None)
        for i, chunk in enumerate(chunked_find(M.User, {}, pagesize=2)):
            log.info('Backfilling login details for chunk #%s', i)
            for u in chunk:
                try:
                    u.backfill_login_details(auth_provider)
                except Exception:
                    log.exception('Error backfilling on user %s', u)

            main_orm_session.clear()  # AuditLog and User objs
            main_explicitflush_orm_session.clear()  # UserLoginDetails objs, already flushed individually

        log.info('Finished backfilling previous login details')


if __name__ == '__main__':
    BackfillPreviousLoginDetails.main()
