from pyforge.tests.helpers import run_app_setup
from pyforge.websetup.bootstrap import clear_all_database_tables


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


class WithDatabase(MockPatchTestCase):
    def setUp(self):
        super(WithDatabase, self).setUp()
        clear_all_database_tables()

