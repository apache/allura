import unittest
import mock

from ming.orm import ThreadLocalORMSession
from pylons import tmpl_context as c

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.lib import helpers as h
from allura.tasks import repo_tasks
from allura import model as M
from forgegit.tests import with_git

class TestGitTasks(unittest.TestCase):

    def setUp(self):
        setup_basic_test()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        setup_global_objects()
        h.set_context('test', 'src-git', neighborhood='Projects')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        repo_tasks.init()

    def test_refresh_commit(self):
        repo_tasks.refresh()

    @with_git
    def test_reclone(self):
        ns = M.Notification.query.find().count()
        with mock.patch.object(c.app.repo, 'init_as_clone') as f:
            c.app.config.options['init_from_path'] = 'test_path'
            c.app.config.options['init_from_url'] = 'test_url'
            repo_tasks.reclone_repo(prefix='p', shortname='test', mount_point='src-git')
            M.main_orm_session.flush()
            f.assert_called_with('test_path', None, 'test_url')
            assert ns + 1 == M.Notification.query.find().count()
