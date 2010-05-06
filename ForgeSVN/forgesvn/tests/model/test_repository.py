import os
import shutil
import unittest
import subprocess
import pkg_resources

from pylons import g

from ming.orm import ThreadLocalORMSession

from pyforge.tests import helpers
from pyforge import model as M
from pyforge.lib import helpers as h
from forgesvn import model as SM

class TestSVN(unittest.TestCase):

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
        shutil.rmtree(os.path.join(repo.fs_path, repo.name))
        repo.init()
        shutil.rmtree(os.path.join(repo.fs_path, repo.name))

    def test_index(self):
        i = self.repo.index()
        assert i['type_s'] == 'SVNRepository', i

    def test_log(self):
        for entry in self.repo.log():
            print entry

