import os
import shutil
import unittest
import pkg_resources

from pylons import c

from ming.orm import ThreadLocalORMSession

from pyforge.tests import helpers
from pyforge.lib import helpers as h
from forgesvn import model as SM

class TestSVNRepo(unittest.TestCase):

    def setUp(self):
        helpers.setup_basic_test()
        helpers.setup_global_objects()
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data')
        self.repo = SM.SVNRepository(
            name='testsvn',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'svn',
            status = 'creating')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        repo = SM.SVNRepository(
            name='testsvn',
            fs_path='/tmp/',
            url_path = '/test/',
            tool = 'svn',
            status = 'creating')
        dirname = os.path.join(repo.fs_path, repo.name)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
        repo.init()
        shutil.rmtree(dirname)

    def test_index(self):
        i = self.repo.index()
        assert i['type_s'] == 'SVNRepository', i

    def test_log(self):
        for entry in self.repo.log():
            assert entry.author_username == 'rick446@usa.net'
            assert entry.message

    def test_revision(self):
        entry = self.repo.revision(1)
        assert entry.author_username == 'rick446@usa.net'
        assert entry.message

    def test_diff(self):
        diff = self.repo.diff(1,2)
        assert '+' in diff


class TestSVNRev(unittest.TestCase):

    def setUp(self):
        helpers.setup_basic_test()
        helpers.setup_global_objects()
        h.set_context('test', 'src')
        repo_dir = pkg_resources.resource_filename(
            'forgesvn', 'tests/data')
        self.repo = SM.SVNRepository(
            name='testsvn',
            fs_path=repo_dir,
            url_path = '/test/',
            tool = 'svn',
            status = 'creating')
        self.rev = self.repo.revision(1)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_ref(self):
        ref = self.rev.dump_ref()
        art = ref.to_artifact()
        assert self.rev._id == art._id

    def test_url(self):
        assert self.rev.url().endswith('/1')

    def test_primary(self):
        assert self.rev.primary() == self.rev

    def test_shorthand(self):
        assert self.rev.shorthand_id() == '[r1]'

    def test_diff(self):
        assert '+' in self.rev.diff()


