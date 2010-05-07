import os
import shutil
import unittest
import pkg_resources

from ming.orm import ThreadLocalORMSession

from pyforge.tests import helpers
from pyforge.lib import helpers as h
from forgehg import model as HM

class TestHgRepo(unittest.TestCase):

    def setUp(self):
        helpers.setup_basic_test()
        helpers.setup_global_objects()
        h.set_context('test', 'src_hg')
        repo_dir = pkg_resources.resource_filename(
            'forgehg', 'tests/data')
        self.repo = HM.HgRepository(
            name='testrepo.hg',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        repo = HM.HgRepository(
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
        assert i['type_s'] == 'HgRepository', i

    def test_log(self):
        committers = set([
                'jwalsh04@gmail.com',
                'rick446@usa.net',
                'jbeard@geek.net'])
        for entry in self.repo.log():
            assert entry.user['email'] in committers, entry.user
            assert entry.description()

    def test_revision(self):
        entry = self.repo.revision('tip')
        assert entry.user['email'] == 'jwalsh04@gmail.com'
        assert entry.description()

    def test_tags(self):
        self.repo.repo_tags()

class TestHgCommit(unittest.TestCase):

    def setUp(self):
        helpers.setup_basic_test()
        helpers.setup_global_objects()
        h.set_context('test', 'src_hg')
        repo_dir = pkg_resources.resource_filename(
            'forgehg', 'tests/data')
        self.repo = HM.HgRepository(
            name='testrepo.hg',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'hg',
            status = 'creating')
        self.rev = self.repo.revision('tip')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_ref(self):
        ref = self.rev.dump_ref()
        art = ref.to_artifact()
        assert self.rev._id == art._id

    def test_url(self):
        assert self.rev.url().endswith('/6cf1b362918b747c873f1903064860726e9360ef')

    def test_user_url(self):
        assert self.rev.user_url is None

    def test_primary(self):
        assert self.rev.primary() == self.rev

    def test_shorthand(self):
        assert self.rev.shorthand_id() == '[6cf1b3]'

    def test_diff(self):
        len(list(self.rev.diffs()))
        for d in self.rev.diffs():
            print d


