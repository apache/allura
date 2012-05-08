import datetime
import unittest

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
