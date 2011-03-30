import unittest
from nose.tools import assert_equals

from tg import c
from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib import helpers as h


class TestSVNApp(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        setup_global_objects()
        h.set_context('test', 'src')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_admin_menu(self):
        assert_equals(len(c.app.admin_menu()), 3)
        assert_equals(c.app.admin_menu()[0].label, 'Viewable Files')

    def test_uninstall(self):
        c.app.uninstall(c.project)
        from allura import model as M
        M.main_orm_session.flush()
        task = M.MonQTask.get()
        assert task.task_name == 'allura.tasks.repo_tasks.uninstall', task.task_name
        task()
