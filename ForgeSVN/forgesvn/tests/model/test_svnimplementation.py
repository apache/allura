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

from mock import Mock, patch
from tg import app_globals as g

from alluratest.controller import setup_unit_test
from allura.model.repository import Commit
from forgesvn.model.svn import SVNImplementation


class TestSVNImplementation:

    def setup_method(self, method):
        setup_unit_test()

    def test_compute_tree_new(self):
        self._test_compute_tree_new('/trunk/foo/')
        self._test_compute_tree_new('/trunk/foo')
        self._test_compute_tree_new('trunk/foo/')
        self._test_compute_tree_new('trunk/foo')

    @patch('allura.model.repository.LastCommitDoc.m.update_partial')
    @patch('allura.model.repository.Tree.upsert')
    @patch('allura.model.repository.Tree.query.get')
    def _test_compute_tree_new(self, path, tree_get, tree_upsert, lcd_partial):
        repo = Mock(fs_path=g.tmpdir + '/')
        repo.name = 'code'
        impl = SVNImplementation(repo)
        impl._svn.info2 = Mock()
        impl._svn.info2.return_value = [('foo', Mock())]
        tree_get.return_value = None  # no existing tree
        commit = Commit()
        commit._id = '5057636b9c1040636b81e4b1:6'
        tree_upsert.return_value = (Mock(), True)

        tree_id = impl.compute_tree_new(commit, path)

        assert (impl._svn.info2.call_args[0]
                     [0] == 'file://' + g.tmpdir + '/code/trunk/foo')
        assert lcd_partial.called

    def test_last_commit_ids(self):
        self._test_last_commit_ids('/trunk/foo/')
        self._test_last_commit_ids('/trunk/foo')
        self._test_last_commit_ids('trunk/foo/')
        self._test_last_commit_ids('trunk/foo')

    def _test_last_commit_ids(self, path):
        repo = Mock(fs_path=g.tmpdir + '/')
        repo.name = 'code'
        repo._id = '5057636b9c1040636b81e4b1'
        impl = SVNImplementation(repo)
        impl._svn.info2 = Mock()
        impl._svn.info2.return_value = [('trunk', Mock()), ('foo', Mock())]
        impl._svn.info2.return_value[1][1].last_changed_rev.number = '1'
        commit = Commit()
        commit._id = '5057636b9c1040636b81e4b1:6'
        entries = impl.last_commit_ids(commit, [path])

        assert entries == {path.strip('/'): '5057636b9c1040636b81e4b1:1'}
        assert (impl._svn.info2.call_args[0]
                     [0] == 'file://' + g.tmpdir + '/code/trunk')

    @patch('forgesvn.model.svn.svn_path_exists')
    def test__tarball_path_clean(self, path_exists):
        repo = Mock(fs_path=g.tmpdir + '/')
        repo.name = 'code'
        repo._id = '5057636b9c1040636b81e4b1'
        impl = SVNImplementation(repo)
        path_exists.return_value = False
        # edge cases
        assert impl._tarball_path_clean(None) == ''
        assert impl._tarball_path_clean('') == ''
        # common
        assert impl._tarball_path_clean('/some/path/') == 'some/path'
        assert impl._tarball_path_clean('some/path') == 'some/path'
        assert impl._tarball_path_clean('/some/path/tags/1.0/some/dir') == 'some/path/tags/1.0/some/dir'
        # with fallback to trunk
        path_exists.return_value = True
        assert impl._tarball_path_clean(None) == 'trunk'
        assert impl._tarball_path_clean('') == 'trunk'

    @patch('forgesvn.model.svn.svn_path_exists')
    def test_update_checkout_url(self, svn_path_exists):
        impl = SVNImplementation(Mock())
        opts = impl._repo.app.config.options = {}

        svn_path_exists.side_effect = lambda path: False
        opts['checkout_url'] = 'invalid'
        impl.update_checkout_url()
        assert opts['checkout_url'] == ''

        svn_path_exists.side_effect = lambda path: path.endswith('trunk')
        opts['checkout_url'] = 'invalid'
        impl.update_checkout_url()
        assert opts['checkout_url'] == 'trunk'

        svn_path_exists.side_effect = lambda path: path.endswith('trunk')
        opts['checkout_url'] = ''
        impl.update_checkout_url()
        assert opts['checkout_url'] == 'trunk'
