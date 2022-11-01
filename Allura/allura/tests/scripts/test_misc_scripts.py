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

from bson import ObjectId

from allura.scripts.clear_old_notifications import ClearOldNotifications
from alluratest.controller import setup_basic_test
from allura import model as M
from ming.odm import session


class TestClearOldNotifications:

    def setup_method(self, method):
        setup_basic_test()

    def run_script(self, options):
        cls = ClearOldNotifications
        opts = cls.parser().parse_args(options)
        cls.execute(opts)

    def test(self):
        n = M.Notification(app_config_id=ObjectId(), neighborhood_id=ObjectId(), project_id=ObjectId(),
                           tool_name='blah')
        session(n).flush(n)
        assert M.Notification.query.find().count() == 1
        self.run_script(['--back-days', '7'])
        assert M.Notification.query.find().count() == 1
        self.run_script(['--back-days', '0'])
        assert M.Notification.query.find().count() == 0
