import unittest
from nose.tools import assert_equals

from pylons import c, g
from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib import helpers as h


class TestGitApp(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        h.set_context('test', 'src-git')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_admin_menu(self):
        assert_equals(len(c.app.admin_menu()), 3)

    def test_uninstall(self):
        c.app.uninstall(c.project)
        from allura import model as M
        M.main_orm_session.flush()
        task = M.MonQTask.get()
        assert task.task_name == 'allura.tasks.repo_tasks.uninstall', task.task_name
        task()
