import unittest

from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib import helpers as h
from allura.tasks import repo_tasks

from forgehg.tests import with_hg

class TestHgReactors(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @with_hg
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-hg', neighborhood='Projects')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        repo_tasks.init()

    def test_refresh_commit(self):
        repo_tasks.refresh()
