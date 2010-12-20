import os
import shutil
import unittest
import pkg_resources

from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib import helpers as h
from forgehg import model as HM

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


