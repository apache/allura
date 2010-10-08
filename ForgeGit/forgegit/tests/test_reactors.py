import unittest

from pylons import c, g

from ming.orm import ThreadLocalORMSession

from allura.tests import helpers
from allura.lib import helpers as h

from allura.lib.repository import RepositoryApp as R

class TestGitReactors(unittest.TestCase):

    def setUp(self):
        helpers.setup_basic_test()
        helpers.setup_global_objects()
        h.set_context('test', 'src-git')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        R._init('repo.init', dict(
                project_id=str(c.project._id),
                mount_point=c.app.config.options.mount_point))

    def test_refresh_commit(self):
        R._refresh('repo.refresh', dict(
                project_id=str(c.project._id),
                mount_point=c.app.config.options.mount_point))
