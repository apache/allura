import unittest

from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib import helpers as h
from allura.tasks import repo_tasks

class TestGitTasks(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        h.set_context('test', 'src-git')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        repo_tasks.init()

    def test_refresh_commit(self):
        repo_tasks.refresh()
