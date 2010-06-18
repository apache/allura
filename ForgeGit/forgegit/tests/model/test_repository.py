import os
import shutil
import unittest
import pkg_resources

from ming.orm import ThreadLocalORMSession

from pyforge.tests import helpers
from pyforge.lib import helpers as h
from forgegit import model as GM

class TestGitRepo(unittest.TestCase):

    def setUp(self):
        helpers.setup_basic_test()
        helpers.setup_global_objects()
        h.set_context('test', 'src-git')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        self.repo = GM.GitRepository(
            name='testgit.git',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'git',
            status = 'creating')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        repo = GM.GitRepository(
            name='testgit.git',
            fs_path='/tmp/',
            url_path = '/test/',
            tool = 'git',
            status = 'creating')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        shutil.rmtree(dirname)

    def test_index(self):
        i = self.repo.index()
        assert i['type_s'] == 'GitRepository', i

    def test_log(self):
        for entry in self.repo.log():
            assert str(entry.author)
            assert entry.message

    def test_commit(self):
        entry = self.repo.commit('HEAD')
        assert str(entry.author) == 'Sebastian Thiel', entry.author
        assert entry.message

    def test_tags(self):
        self.repo.repo_tags()

class TestGitCommit(unittest.TestCase):

    def setUp(self):
        helpers.setup_basic_test()
        helpers.setup_global_objects()
        h.set_context('test', 'src')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        self.repo = GM.GitRepository(
            name='testgit.git',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'git',
            status = 'creating')
        self.rev = self.repo.commit('HEAD')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_ref(self):
        ref = self.rev.dump_ref()
        art = ref.to_artifact()
        assert self.rev._id == art._id

    def test_url(self):
        assert self.rev.url().endswith('3061/')

    def test_committer_url(self):
        assert self.rev.committer_url is None

    def test_primary(self):
        assert self.rev.primary() == self.rev

    def test_shorthand(self):
        assert len(self.rev.shorthand_id()) == 8

    def test_diff(self):
        len(self.rev.diff())
        for d in self.rev.diff():
            print d


