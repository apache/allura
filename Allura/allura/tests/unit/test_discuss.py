from nose.tools import assert_false, assert_true

from allura import model as M
from allura.tests.unit import WithDatabase
from allura.tests.unit.patches import fake_app_patch


class TestThread(WithDatabase):
    patches = [fake_app_patch]

    def test_should_update_index(self):
        p = M.Thread()
        assert_false(p.should_update_index({}, {}))
        old = {'num_views': 1}
        new = {'num_views': 2}
        assert_false(p.should_update_index(old, new))
        old = {'num_views': 1, 'a': 1}
        new = {'num_views': 2, 'a': 1}
        assert_false(p.should_update_index(old, new))
        old = {'num_views': 1, 'a': 1}
        new = {'num_views': 2, 'a': 2}
        assert_true(p.should_update_index(old, new))
