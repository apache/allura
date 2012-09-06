import datetime
import unittest
from mock import patch, Mock

from allura import model as M
from allura.controllers.repository import topo_sort
from alluratest.controller import setup_unit_test

class TestCommitRunBuilder(unittest.TestCase):

    def setUp(self):
        setup_unit_test()
        commits = [
            M.repo.CommitDoc.make(dict(
                _id=str(i)))
            for i in range(10) ]
        for p,c in zip(commits, commits[1:]):
            p.child_ids = [ c._id ]
            c.parent_ids = [ p._id ]
        for ci in commits:
            ci.m.save()
        self.commits = commits

    def test_single_pass(self):
        crb = M.repo_refresh.CommitRunBuilder(
            [ci._id for ci in self.commits])
        crb.run()
        self.assertEqual(M.repo.CommitRunDoc.m.count(), 1)

    def test_two_pass(self):
        crb = M.repo_refresh.CommitRunBuilder(
            [ci._id for ci in self.commits[:5]])
        crb.run()
        crb = M.repo_refresh.CommitRunBuilder(
            [ci._id for ci in self.commits[5:]])
        crb.run()
        self.assertEqual(M.repo.CommitRunDoc.m.count(), 2)
        crb.cleanup()
        self.assertEqual(M.repo.CommitRunDoc.m.count(), 1)

    def test_svn_like(self):
        for ci in self.commits:
            crb = M.repo_refresh.CommitRunBuilder([ci._id])
            crb.run()
            crb.cleanup()
        self.assertEqual(M.repo.CommitRunDoc.m.count(), 1)

    def test_reversed(self):
        for ci in reversed(self.commits):
            crb = M.repo_refresh.CommitRunBuilder([ci._id])
            crb.run()
            crb.cleanup()
        self.assertEqual(M.repo.CommitRunDoc.m.count(), 1)

class TestTopoSort(unittest.TestCase):
    def test_commit_dates_out_of_order(self):
        """Commits should be sorted by their parent/child relationships,
        regardless of the date on the commit.
        """
        head_ids = ['dev', 'master']
        parents = {
            'dev':        ['dev@{1}'],
            'dev@{1}':    ['master'],
            'master':     ['master@{1}'],
            'master@{1}': ['master@{2}'],
            'master@{2}': ['master@{3}'],
            'master@{3}': []}
        children = {
            'master@{3}': ['master@{2}'],
            'master@{2}': ['master@{1}'],
            'master@{1}': ['master'],
            'master':     ['dev@{1}'],
            'dev@{1}':    ['dev'],
            'dev':        []}
        dates = {
            'dev@{1}':    datetime.datetime(2012, 1, 1),
            'master@{3}': datetime.datetime(2012, 2, 1),
            'master@{2}': datetime.datetime(2012, 3, 1),
            'master@{1}': datetime.datetime(2012, 4, 1),
            'master':     datetime.datetime(2012, 5, 1),
            'dev':        datetime.datetime(2012, 6, 1)}
        result = topo_sort(children, parents, dates, head_ids)
        self.assertEqual(list(result), ['dev', 'dev@{1}', 'master',
            'master@{1}', 'master@{2}', 'master@{3}'])


def tree(name, id, trees=None, blobs=None):
    t = Mock(tree_ids=[], blob_ids=[], other_ids=[])
    t.name = name
    t.id = id
    t._id = id
    if trees is not None:
        t.tree_ids = trees
    if blobs is not None:
        t.blob_ids = blobs
    return t


def blob(name, id):
    b = Mock()
    b.name = name
    b.id = id
    return b


class TestRefreshLastCommit(unittest.TestCase):
    @patch('allura.model.repo_refresh.TreeDoc.m.get')
    @patch('allura.model.repo_refresh.set_last_commit')
    def test_no_changes(self, set_last_commit, get):
        repo_id = 'repo_1'
        path = '/'
        lhs_tree = tree('lhs_tree', 'tid1')
        rhs_tree = tree('rhs_tree', 'tid1')
        parent_tree = Mock()
        commit_info = {}

        M.repo_refresh.refresh_last_commit(repo_id, path, rhs_tree, lhs_tree, parent_tree, commit_info)

        self.assertEqual(set_last_commit.call_count, 0)
        self.assertEqual(get.call_count, 0)

    @patch('allura.model.repo_refresh.TreeDoc.m.get')
    @patch('allura.model.repo_refresh.set_last_commit')
    def test_unchanged_blob(self, set_last_commit, get):
        repo_id = 'repo_1'
        path = '/'
        lhs_tree = tree('lhs_tree', 'tid1', blobs=[blob('unchanged_blob', 'bid1')])
        rhs_tree = tree('rhs_tree', 'tid2', blobs=[blob('unchanged_blob', 'bid1')])
        parent_tree = Mock()
        commit_info = {}

        M.repo_refresh.refresh_last_commit(repo_id, path, rhs_tree, lhs_tree, parent_tree, commit_info)

        self.assertEqual(set_last_commit.call_count, 0)
        self.assertEqual(get.call_count, 0)

    @patch('allura.model.repo_refresh.TreeDoc.m.get')
    @patch('allura.model.repo_refresh.set_last_commit')
    def test_changed_blob(self, set_last_commit, get):
        repo_id = 'repo_1'
        path = '/'
        lhs_tree = tree('lhs_tree', 'tid1', blobs=[blob('changed_blob', 'bid1')])
        rhs_tree = tree('rhs_tree', 'tid2', blobs=[blob('changed_blob', 'bid2')])
        parent_tree = Mock()
        commit_info = {'author': 'Testy'}

        M.repo_refresh.refresh_last_commit(repo_id, path, rhs_tree, lhs_tree, parent_tree, commit_info)

        set_last_commit.assert_called_once_with(repo_id, path, 'changed_blob', 'bid2', commit_info)
        self.assertEqual(get.call_count, 0)

    @patch('allura.model.repo_refresh.TreeDoc.m.get')
    @patch('allura.model.repo_refresh.set_last_commit')
    def test_new_blob(self, set_last_commit, get):
        repo_id = 'repo_1'
        path = '/'
        lhs_tree = tree('lhs_tree', 'tid1', blobs=[blob('old_blob', 'bid1')])
        rhs_tree = tree('rhs_tree', 'tid2', blobs=[blob('new_blob', 'bid2')])
        parent_tree = Mock()
        commit_info = {'author': 'Testy'}

        M.repo_refresh.refresh_last_commit(repo_id, path, rhs_tree, lhs_tree, parent_tree, commit_info)

        set_last_commit.assert_called_once_with(repo_id, path, 'new_blob', 'bid2', commit_info)
        self.assertEqual(get.call_count, 0)

    @patch('allura.model.repo_refresh.TreeDoc.m.get')
    @patch('allura.model.repo_refresh.set_last_commit')
    def test_unchanged_subtree(self, set_last_commit, get):
        repo_id = 'repo_1'
        path = '/'
        lhs_tree = tree('lhs_tree', 'tid1', trees=[tree('unchanged_tree', 'tid3')])
        rhs_tree = tree('rhs_tree', 'tid2', trees=[tree('unchanged_tree', 'tid3', blobs=[blob('new_blob', 'bid1')])])
        parent_tree = Mock()
        commit_info = {'author': 'Testy'}
        get.side_effect = [rhs_tree.tree_ids[0], lhs_tree.tree_ids[0]]

        M.repo_refresh.refresh_last_commit(repo_id, path, rhs_tree, lhs_tree, parent_tree, commit_info)

        self.assertEqual(set_last_commit.call_count, 0)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list, [[{'_id': 'tid3'}], [{'_id': 'tid3'}]])

    @patch('allura.model.repo_refresh.TreeDoc.m.get')
    @patch('allura.model.repo_refresh.set_last_commit')
    def test_changed_subtree(self, set_last_commit, get):
        repo_id = 'repo_1'
        path = '/'
        lhs_tree = tree('lhs_tree', 'tid1', trees=[tree('changed_tree', 'tid3')])
        rhs_tree = tree('rhs_tree', 'tid2', trees=[tree('changed_tree', 'tid4', blobs=[blob('new_blob', 'bid1')])])
        parent_tree = Mock()
        commit_info = {'author': 'Testy'}
        get.side_effect = [rhs_tree.tree_ids[0], lhs_tree.tree_ids[0]]

        M.repo_refresh.refresh_last_commit(repo_id, path, rhs_tree, lhs_tree, parent_tree, commit_info)

        self.assertEqual(set_last_commit.call_count, 2)
        self.assertEqual(set_last_commit.call_args_list, [
            [(repo_id, '/', 'changed_tree', 'tid4', commit_info)],
            [(repo_id, '/changed_tree/', 'new_blob', 'bid1', commit_info)],
        ])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list, [[{'_id': 'tid4'}], [{'_id': 'tid3'}]])


class TestTree(unittest.TestCase):

    @patch('allura.model.repo.Tree.__getitem__')
    def test_get_obj_by_path(self, getitem):
        tree = M.repo.Tree()
        # test with relative path
        tree.get_obj_by_path('some/path/file.txt')
        getitem.assert_called_with('some')
        getitem().__getitem__.assert_called_with('path')
        getitem().__getitem__().__getitem__.assert_called_with('file.txt')
        # test with absolute path
        tree.get_obj_by_path('/some/path/file.txt')
        getitem.assert_called_with('some')
        getitem().__getitem__.assert_called_with('path')
        getitem().__getitem__().__getitem__.assert_called_with('file.txt')
