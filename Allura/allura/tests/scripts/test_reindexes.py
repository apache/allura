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
from testfixtures import LogCapture

from allura.scripts.reindex_projects import ReindexProjects
from allura.scripts.reindex_users import ReindexUsers
from allura.tests.decorators import assert_logmsg_and_no_warnings_or_errors
from alluratest.controller import setup_basic_test
from allura import model as M


class TestReindexProjects:

    def setup_method(self, method):
        setup_basic_test()

    def run_script(self, options):
        cls = ReindexProjects
        opts = cls.parser().parse_args(options)
        cls.execute(opts)

    def test(self):
        with LogCapture() as logs:
            self.run_script(['-n', '/p/', '-p', 'test'])
        assert_logmsg_and_no_warnings_or_errors(logs, 'Reindex project test')
        assert_logmsg_and_no_warnings_or_errors(logs, 'Reindex done')

    def test_with_tasks(self):
        with LogCapture() as logs:
            self.run_script(['-n', '/p/', '-p', 'test', '--tasks'])
        assert_logmsg_and_no_warnings_or_errors(logs, 'Reindex project test')
        assert_logmsg_and_no_warnings_or_errors(logs, 'Reindex queued')
        assert M.MonQTask.query.find({'task_name': 'allura.tasks.index_tasks.add_projects'}).count() == 1


class TestReindexUsers:

    def setup_method(self, method):
        setup_basic_test()

    def run_script(self, options):
        cls = ReindexUsers
        opts = cls.parser().parse_args(options)
        cls.execute(opts)

    def test(self):
        with LogCapture() as logs:
            self.run_script([])
        assert_logmsg_and_no_warnings_or_errors(logs, 'Reindex user root')
        assert_logmsg_and_no_warnings_or_errors(logs, 'Reindex user test-user-1')
        assert_logmsg_and_no_warnings_or_errors(logs, 'Reindex done')

    def test_with_tasks(self):
        with LogCapture() as logs:
            self.run_script(['--tasks'])
        assert_logmsg_and_no_warnings_or_errors(logs, 'Reindex user root')
        assert_logmsg_and_no_warnings_or_errors(logs, 'Reindex user test-user-1')
        assert_logmsg_and_no_warnings_or_errors(logs, 'Reindex queued')
        assert M.MonQTask.query.find({'task_name': 'allura.tasks.index_tasks.add_users'}).count() == 1
