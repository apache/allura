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

