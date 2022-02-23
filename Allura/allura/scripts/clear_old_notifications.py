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

from datetime import datetime, timedelta

import logging

import argparse

from allura.scripts import ScriptTask
from allura import model as M

log = logging.getLogger('allura.scripts.clear_old_notifications')


class ClearOldNotifications(ScriptTask):

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(description="Remove old temporary notifications")
        parser.add_argument('--back-days', dest='back_days', type=float, default=60,
                            help='How many days back to clear from (keeps newer notifications)')
        return parser

    @classmethod
    def execute(cls, options):
        before = datetime.utcnow() - timedelta(days=options.back_days)
        M.Notification.query.remove({
            'pubdate': {'$lt': before}
        })


def get_parser():
    return ClearOldNotifications.parser()


if __name__ == '__main__':
    ClearOldNotifications.main()
