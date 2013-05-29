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

from mock import Mock, MagicMock, patch
import pysvn
from nose.tools import assert_equal
from pylons import app_globals as g

from allura.model.repo import Commit
from forgesvn.model.svn import Repository, SVNImplementation


class TestSVNImplementation(object):

    def test_compute_tree_new(self):
        self._test_compute_tree_new('/trunk/foo/')
        self._test_compute_tree_new('/trunk/foo')
        self._test_compute_tree_new('trunk/foo/')
        self._test_compute_tree_new('trunk/foo')

    @patch('allura.model.repo.LastCommitDoc.m.update_partial')
    @patch('allura.model.repo.TreesDoc.m.update_partial')
    @patch('allura.model.repo.Tree.upsert')
    @patch('allura.model.repo.Tree.query.get')
    def _test_compute_tree_new(self, path, tree_get, tree_upsert, treesdoc_partial, lcd_partial):
        repo = Mock(fs_path=g.tmpdir+'/')
        repo.name = 'code'
        impl = SVNImplementation(repo)
        impl._svn.info2 = Mock()
        impl._svn.info2.return_value = [('foo', Mock())]
        tree_get.return_value = None  # no existing tree
        commit = Commit()
        commit._id = '5057636b9c1040636b81e4b1:6'
        tree_upsert.return_value = (Mock(), True)

        tree_id = impl.compute_tree_new(commit, path)

        assert_equal(impl._svn.info2.call_args[0][0], 'file://'+g.tmpdir+'/code/trunk/foo')
        treesdoc_partial.assert_called()
        lcd_partial.assert_called()


    def test_last_commit_ids(self):
        self._test_last_commit_ids('/trunk/foo/')
        self._test_last_commit_ids('/trunk/foo')
        self._test_last_commit_ids('trunk/foo/')
        self._test_last_commit_ids('trunk/foo')

    def _test_last_commit_ids(self, path):
        repo = Mock(fs_path=g.tmpdir+'/')
        repo.name = 'code'
        repo._id = '5057636b9c1040636b81e4b1'
        impl = SVNImplementation(repo)
        impl._svn.info2 = Mock()
        impl._svn.info2.return_value = [('trunk', Mock()), ('foo', Mock())]
        impl._svn.info2.return_value[1][1].last_changed_rev.number = '1'
        commit = Commit()
        commit._id = '5057636b9c1040636b81e4b1:6'
        entries = impl.last_commit_ids(commit, [path])

        assert_equal(entries, {path.strip('/'): '5057636b9c1040636b81e4b1:1'})
        assert_equal(impl._svn.info2.call_args[0][0], 'file://'+g.tmpdir+'/code/trunk')

    @patch('forgesvn.model.svn.svn_path_exists')
    def test__path_to_root(self, path_exists):
        repo = Mock(fs_path=g.tmpdir+'/')
        repo.name = 'code'
        repo._id = '5057636b9c1040636b81e4b1'
        impl = SVNImplementation(repo)
        path_exists.return_value = False
        # edge cases
        assert_equal(impl._path_to_root(None), '')
        assert_equal(impl._path_to_root(''), '')
        assert_equal(impl._path_to_root('/some/path/'), '')
        assert_equal(impl._path_to_root('some/path'), '')
        # tags
        assert_equal(impl._path_to_root('/some/path/tags/1.0/some/dir'), 'some/path/tags/1.0')
        assert_equal(impl._path_to_root('/some/path/tags/1.0/'), 'some/path/tags/1.0')
        assert_equal(impl._path_to_root('/some/path/tags/'), '')
        # branches
        assert_equal(impl._path_to_root('/some/path/branches/b1/dir'), 'some/path/branches/b1')
        assert_equal(impl._path_to_root('/some/path/branches/b1/'), 'some/path/branches/b1')
        assert_equal(impl._path_to_root('/some/path/branches/'), '')
        # trunk
        assert_equal(impl._path_to_root('/some/path/trunk/some/dir/'), 'some/path/trunk')
        assert_equal(impl._path_to_root('/some/path/trunk'), 'some/path/trunk')
        # with fallback to trunk
        path_exists.return_value = True
        assert_equal(impl._path_to_root(''), 'trunk')
        assert_equal(impl._path_to_root('/some/path/'), 'trunk')
        assert_equal(impl._path_to_root('/tags/'), 'trunk')
        assert_equal(impl._path_to_root('/branches/'), 'trunk')
        assert_equal(impl._path_to_root('/tags/1.0'), 'tags/1.0')
        assert_equal(impl._path_to_root('/branches/branch'), 'branches/branch')
