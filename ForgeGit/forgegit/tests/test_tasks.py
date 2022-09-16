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
import unittest
import mock
from testfixtures import LogCapture

from ming.orm import ThreadLocalORMSession
from tg import tmpl_context as c

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.scripts.refreshrepo import RefreshRepo
from allura.scripts.refresh_last_commits import RefreshLastCommits
from allura.lib import helpers as h
from allura.tasks import repo_tasks
from allura.tests.decorators import assert_logmsg_and_no_warnings_or_errors
from allura import model as M
from forgegit.tests import with_git
from forgegit.tests.functional.test_controllers import _TestCase as GitRealDataBaseTestCase


class TestGitTasks(unittest.TestCase):

    def setup_method(self, method):
        setup_basic_test()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-git', neighborhood='Projects')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        repo_tasks.init()

    def test_refresh_commit(self):
        repo_tasks.refresh()

    @with_git
    def test_reclone(self):
        ns = M.Notification.query.find().count()
        with mock.patch.object(c.app.repo, 'init_as_clone') as f:
            c.app.config.options['init_from_path'] = 'test_path'
            c.app.config.options['init_from_url'] = 'test_url'
            repo_tasks.reclone_repo(
                prefix='p', shortname='test', mount_point='src-git')
            M.main_orm_session.flush()
            f.assert_called_with('test_path', None, 'test_url')
            assert ns + 1 == M.Notification.query.find().count()


class TestCoreAlluraTasks(GitRealDataBaseTestCase):
    """
    Not git-specific things we are testing, but the git tool is a useful standard repo type to use for it
    """

    def setup_method(self, method):
        super().setup_method(method)
        self.setup_with_tools()

    def test_refreshrepo(self):
        opts = RefreshRepo.parser().parse_args(
            ['--nbhd', '/p/', '--project', 'test', '--clean', '--all', '--repo-types', 'git'])
        with LogCapture() as logs:
            RefreshRepo.execute(opts)
        assert_logmsg_and_no_warnings_or_errors(logs, 'Refreshing ALL commits in ')

        # run again with some different params
        opts = RefreshRepo.parser().parse_args(
            ['--nbhd', '/p/', '--project', 'test', '--clean-after', '2010-01-01T00:00:00'])
        with LogCapture() as logs:
            RefreshRepo.execute(opts)
        assert_logmsg_and_no_warnings_or_errors(logs, 'Refreshing NEW commits in ')

    def test_refresh_last_commits(self):
        repo = c.app.repo
        repo.refresh()

        opts = RefreshLastCommits.parser().parse_args(
            ['--nbhd', '/p/', '--project', 'test', '--clean', '--repo-types', 'git'])
        with LogCapture() as logs:
            RefreshLastCommits.execute(opts)

        assert_logmsg_and_no_warnings_or_errors(logs, 'Refreshing all last commits ')

        # mostly just making sure nothing errored, but here's at least one thing we can assert:
        assert repo.status == 'ready'

