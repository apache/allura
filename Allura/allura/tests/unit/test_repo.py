import datetime
import unittest
from mock import patch, Mock, MagicMock, call
from nose.tools import assert_equal

from pylons import tmpl_context as c

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


class TestBlob(unittest.TestCase):
    def test_context_no_create(self):
        blob = M.repo.Blob(Mock(), Mock(), Mock())
        blob.path = Mock(return_value='path')
        blob.prev_commit = Mock()
        blob.next_commit = Mock()
        blob.prev_commit.get_path.return_value = '_prev'
        blob.next_commit.get_path.return_value = '_next'
        context = blob.context()
        assert_equal(context, {'prev': '_prev', 'next': '_next'})
        blob.prev_commit.get_path.assert_called_with('path', create=False)
        blob.next_commit.get_path.assert_called_with('path', create=False)

        blob.prev_commit.get_path.side_effect = KeyError
        blob.next_commit.get_path.side_effect = KeyError
        context = blob.context()
        assert_equal(context, {'prev': None, 'next': None})

    @patch.object(M.repo.LastCommit, '_prev_commit_id')
    def test_prev_commit_no_create(self, lc_pcid):
        lc_pcid.return_value = None
        blob = M.repo.Blob(Mock(), 'foo', 'bid')
        blob.tree.path.return_value = '/path/'
        pc = blob.prev_commit
        lc_pcid.assert_called_once_with(blob.commit, 'path/foo')
        assert not blob.repo.commit.called
        assert_equal(pc, None)

        lc_pcid.reset_mock()
        lc_pcid.return_value = 'pcid'
        blob = M.repo.Blob(Mock(), 'foo', 'bid')
        blob.tree.path.return_value = '/path/'
        blob.repo.commit.return_value = 'commit'
        pc = blob.prev_commit
        lc_pcid.assert_called_once_with(blob.commit, 'path/foo')
        blob.repo.commit.assert_called_once_with('pcid')
        assert_equal(pc, 'commit')

    def test_next_commit_no_create(self):
        blob = M.repo.Blob(MagicMock(), MagicMock(), MagicMock())
        blob._id = 'blob1'
        blob.path = Mock(return_value='path')
        blob.commit.context().__getitem__.return_value = None
        nc = blob.next_commit
        assert_equal(nc, None)

        _next = MagicMock()
        _next.context().__getitem__.return_value = None
        _next.get_path.return_value = Mock(_id='blob2')
        blob = M.repo.Blob(MagicMock(), MagicMock(), MagicMock())
        blob._id = 'blob1'
        blob.path = Mock(return_value='path')
        blob.commit.context().__getitem__.return_value = [_next]
        nc = blob.next_commit
        _next.get_path.assert_called_with('path', create=False)
        assert_equal(nc, _next)


class TestCommit(unittest.TestCase):
    def test_get_path_no_create(self):
        commit = M.repo.Commit()
        commit.get_tree = MagicMock()
        commit.get_path('foo/', create=False)
        commit.get_tree.assert_called_with(False)
        commit.get_tree().__getitem__.assert_called_with('foo')
        commit.get_tree().__getitem__.assert_not_called_with('')

    def test_get_tree_no_create(self):
        c.model_cache = Mock()
        c.model_cache.get.return_value = None
        commit = M.repo.Commit()
        commit.repo = Mock()

        commit.tree_id = None
        tree = commit.get_tree(create=False)
        assert not commit.repo.compute_tree_new.called
        assert not c.model_cache.get.called
        assert_equal(tree, None)

        commit.tree_id = 'tree'
        tree = commit.get_tree(create=False)
        assert not commit.repo.compute_tree_new.called
        c.model_cache.get.assert_called_with(M.repo.Tree, dict(_id='tree'))
        assert_equal(tree, None)

        _tree = Mock()
        c.model_cache.get.return_value = _tree
        tree = commit.get_tree(create=False)
        _tree.set_context.assert_called_with(commit)
        assert_equal(tree, _tree)

    @patch.object(M.repo.Tree.query, 'get')
    def test_get_tree_create(self, tree_get):
        c.model_cache = Mock()
        c.model_cache.get.return_value = None
        commit = M.repo.Commit()
        commit.repo = Mock()

        commit.repo.compute_tree_new.return_value = None
        commit.tree_id = None
        tree = commit.get_tree()
        commit.repo.compute_tree_new.assert_called_once_with(commit)
        assert not c.model_cache.get.called
        assert not tree_get.called
        assert_equal(tree, None)

        commit.repo.compute_tree_new.reset_mock()
        commit.repo.compute_tree_new.return_value = 'tree'
        _tree = Mock()
        c.model_cache.get.return_value = _tree
        tree = commit.get_tree()
        commit.repo.compute_tree_new.assert_called_once_with(commit)
        assert not tree_get.called
        c.model_cache.get.assert_called_once_with(M.repo.Tree, dict(_id='tree'))
        _tree.set_context.assert_called_once_with(commit)
        assert_equal(tree, _tree)

        commit.repo.compute_tree_new.reset_mock()
        c.model_cache.get.reset_mock()
        commit.tree_id = 'tree2'
        tree = commit.get_tree()
        assert not commit.repo.compute_tree_new.called
        assert not tree_get.called
        c.model_cache.get.assert_called_once_with(M.repo.Tree, dict(_id='tree2'))
        _tree.set_context.assert_called_once_with(commit)
        assert_equal(tree, _tree)

        commit.repo.compute_tree_new.reset_mock()
        c.model_cache.get.reset_mock()
        c.model_cache.get.return_value = None
        tree_get.return_value = _tree
        tree = commit.get_tree()
        c.model_cache.get.assert_called_once_with(M.repo.Tree, dict(_id='tree2'))
        commit.repo.compute_tree_new.assert_called_once_with(commit)
        assert_equal(commit.tree_id, 'tree')
        tree_get.assert_called_once_with(_id='tree')
        c.model_cache.set.assert_called_once_with(M.repo.Tree, dict(_id='tree'), _tree)
        _tree.set_context.assert_called_once_with(commit)
        assert_equal(tree, _tree)

    def test_tree_create(self):
        commit = M.repo.Commit()
        commit.get_tree = Mock()
        tree = commit.tree
        commit.get_tree.assert_called_with(create=True)
