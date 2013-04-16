from mock import Mock, MagicMock, patch
import pysvn
from nose.tools import assert_equal

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
        repo = Mock(fs_path='/tmp/')
        repo.name = 'code'
        impl = SVNImplementation(repo)
        impl._svn.info2 = Mock()
        impl._svn.info2.return_value = [('foo', Mock())]
        tree_get.return_value = None  # no existing tree
        commit = Commit()
        commit._id = '5057636b9c1040636b81e4b1:6'
        tree_upsert.return_value = (Mock(), True)

        tree_id = impl.compute_tree_new(commit, path)

        assert_equal(impl._svn.info2.call_args[0][0], 'file:///tmp/code/trunk/foo')
        treesdoc_partial.assert_called()
        lcd_partial.assert_called()


    def test_last_commit_ids(self):
        self._test_last_commit_ids('/trunk/foo/')
        self._test_last_commit_ids('/trunk/foo')
        self._test_last_commit_ids('trunk/foo/')
        self._test_last_commit_ids('trunk/foo')

    def _test_last_commit_ids(self, path):
        repo = Mock(fs_path='/tmp/')
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
        assert_equal(impl._svn.info2.call_args[0][0], 'file:///tmp/code/trunk')
