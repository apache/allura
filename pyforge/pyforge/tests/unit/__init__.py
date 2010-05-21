from pylons import c
from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.tests.helpers import run_app_setup
from pyforge.websetup import bootstrap
from pyforge.lib import helpers
from pyforge import model


def setUp(self):
    run_app_setup()


class MockPatchTestCase(object):
    patches = []

    def setUp(self):
        self._patch_instances = [patch_fn(self) for patch_fn in self.patches]
        for patch_instance in self._patch_instances:
            patch_instance.__enter__()

    def tearDown(self):
        for patch_instance in self._patch_instances:
            patch_instance.__exit__()


class ForgeTestWithModel(object):
    def setUp(self):
        bootstrap.wipe_database()
        neighborhood = model.Neighborhood(name='Projects',
                                          url_prefix='/p/',
                                          acl=dict(read=[None], create=[],
                                                   moderate=[c.user._id], admin=[c.user._id]))
        c.project = neighborhood.register_project('test', c.user)
        app = c.project.install_app('Tickets', 'bugs')
        ThreadLocalORMSession.flush_all()
        helpers.set_context('test', 'bugs')

    def tearDown(self):
        ThreadLocalORMSession.close_all()

