from nose.tools import assert_equal
from pylons import c

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M

class TestGitLikeTree(object):

    def test_set_blob(self):
        tree = M.GitLikeTree()
        tree.set_blob('/dir/dir2/file', 'file-oid')

        assert_equal(tree.blobs, {})
        assert_equal(tree.get_tree('dir').blobs, {})
        assert_equal(tree.get_tree('dir').get_tree('dir2').blobs, {'file': 'file-oid'})

    def test_hex(self):
        tree = M.GitLikeTree()
        tree.set_blob('/dir/dir2/file', 'file-oid')
        hex = tree.hex()

        # check the reprs. In case hex (below) fails, this'll be useful
        assert_equal(repr(tree.get_tree('dir').get_tree('dir2')), 'b file-oid file')
        assert_equal(repr(tree), 't 96af1772ecce1e6044e6925e595d9373ffcd2615 dir')
        # the hex() value shouldn't change, it's an important key
        assert_equal(hex, '4abba29a43411b9b7cecc1a74f0b27920554350d')

        # another one should be the same
        tree2 = M.GitLikeTree()
        tree2.set_blob('/dir/dir2/file', 'file-oid')
        hex2 = tree2.hex()
        assert_equal(hex, hex2)


class RepoImplTestBase(object):

    def test_commit_run(self):
        M.repo.CommitRunDoc.m.remove()
        commit_ids = list(self.repo.all_commit_ids())
        # simulate building up a commit run from multiple pushes
        for c_id in commit_ids:
            crb = M.repo_refresh.CommitRunBuilder([c_id])
            crb.run()
            crb.cleanup()
        runs = M.repo.CommitRunDoc.m.find().all()
        self.assertEqual(len(runs), 1)
        run = runs[0]
        self.assertEqual(run.commit_ids, commit_ids)
        self.assertEqual(len(run.commit_ids), len(run.commit_times))
        self.assertEqual(run.parent_commit_ids, [])

    def test_repair_commit_run(self):
        commit_ids = list(self.repo.all_commit_ids())
        # simulate building up a commit run from multiple pushes, but skip the
        # last commit to simulate a broken commit run
        for c_id in commit_ids[:-1]:
            crb = M.repo_refresh.CommitRunBuilder([c_id])
            crb.run()
            crb.cleanup()
        # now repair the commitrun by rebuilding with all commit ids
        crb = M.repo_refresh.CommitRunBuilder(commit_ids)
        crb.run()
        crb.cleanup()
        runs = M.repo.CommitRunDoc.m.find().all()
        self.assertEqual(len(runs), 1)
        run = runs[0]
        self.assertEqual(run.commit_ids, commit_ids)
        self.assertEqual(len(run.commit_ids), len(run.commit_times))
        self.assertEqual(run.parent_commit_ids, [])
