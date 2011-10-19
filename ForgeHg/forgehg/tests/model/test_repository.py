import os
import shutil
import unittest
import pkg_resources

from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib import helpers as h
from allura import model as M
from forgehg import model as HM

class TestNewRepo(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        h.set_context('test', 'src')
        repo_dir = pkg_resources.resource_filename(
            'forgehg', 'tests/data')
        self.repo = HM.Repository(
            name='testrepo.hg',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        self.repo.refresh()
        self.rev = M.repo.Commit.query.get(_id=self.repo.heads[0]['object_id'])
        self.rev.repo = self.repo
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_redo_trees(self):
        old_tree = self.rev.tree
        del self.rev.tree
        M.repo.Tree.query.remove()
        ThreadLocalORMSession.close_all()
        new_tree =  self.rev.tree
        self.assertEqual(old_tree.tree_ids, new_tree.tree_ids)
        self.assertEqual(old_tree.blob_ids, new_tree.blob_ids)
        self.assertEqual(old_tree._id, new_tree._id)

    def test_commit(self):
        assert self.rev.primary() is self.rev
        assert self.rev.index_id().startswith('allura/model/repo/Commit#')
        self.rev.author_url
        self.rev.committer_url
        assert self.rev.tree._id == self.rev.tree_id
        assert self.rev.summary == self.rev.message.splitlines()[0]
        assert self.rev.shorthand_id() == '[1c7eb5]'
        assert self.rev.symbolic_ids == (['default'], ['tip'])
        assert self.rev.url() == (
            '/p/test/src/ci/'
            '1c7eb55bbd66ff45906b4a25d4b403899e0ffff1/')
        all_cis = self.rev.log(0, 1000)
        assert len(all_cis) == 5
        assert self.rev.log(1,1000) == all_cis[1:]
        assert self.rev.log(0,3) == all_cis[:3]
        assert self.rev.log(1,2) == all_cis[1:3]
        for ci in all_cis:
            ci.count_revisions()
            ci.context()
        self.rev.tree.ls()
        assert self.rev.tree.readme() == (
            'README', '<pre>This is readme\nAnother line\n</pre>')
        assert self.rev.tree.path() == '/'
        assert self.rev.tree.url() == (
            '/p/test/src/ci/'
            '1c7eb55bbd66ff45906b4a25d4b403899e0ffff1/'
            'tree/')
        self.rev.tree.by_name['README']
        assert self.rev.tree.is_blob('README') == True

class TestHgRepo(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        h.set_context('test', 'src-hg')
        repo_dir = pkg_resources.resource_filename(
            'forgehg', 'tests/data')
        self.repo = HM.Repository(
            name='testrepo.hg',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        self.repo.refresh()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        repo = HM.Repository(
            name='testrepo.hg',
            fs_path='/tmp/',
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        shutil.rmtree(dirname)

    def test_clone(self):
        repo = HM.Repository(
            name='testrepo.hg',
            fs_path='/tmp/',
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        repo_path = pkg_resources.resource_filename(
            'forgehg', 'tests/data/testrepo.hg')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        repo._impl.clone_from(repo_path)
        assert len(repo.log())
        shutil.rmtree(dirname)

    def test_index(self):
        i = self.repo.index()
        assert i['type_s'] == 'Hg Repository', i

    def test_log(self):
        for entry in self.repo.log():
            if entry.object_id.startswith('00000000'): continue
            assert entry.committed.email == 'rick446@usa.net'
            assert entry.message

    def test_revision(self):
        entry = self.repo.commit('tip')
        assert entry.committed.email == 'rick446@usa.net'
        assert entry.message

class TestHgCommit(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        h.set_context('test', 'src-hg')
        repo_dir = pkg_resources.resource_filename(
            'forgehg', 'tests/data')
        self.repo = HM.Repository(
            name='testrepo.hg',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        self.repo.refresh()
        self.rev = self.repo.commit('tip')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_redo_trees(self):
        old_tree = self.rev.tree
        del self.rev.tree
        M.Tree.query.remove(dict(type='tree'))
        ThreadLocalORMSession.close_all()
        new_tree =  self.rev.tree
        self.assertEqual(old_tree.object_ids, new_tree.object_ids)
        self.assertEqual(old_tree.object_id, new_tree.object_id)

    def test_url(self):
        assert self.rev.url().endswith('0ffff1/'), \
            self.rev.url()

    def test_committer_url(self):
        assert self.rev.committer_url is None

    def test_primary(self):
        assert self.rev.primary() == self.rev

    def test_shorthand(self):
        assert len(self.rev.shorthand_id()) == 8

    def test_diff(self):
        diffs = (self.rev.diffs.added
                 +self.rev.diffs.removed
                 +self.rev.diffs.changed
                 +self.rev.diffs.copied)
        for d in diffs:
            print d


