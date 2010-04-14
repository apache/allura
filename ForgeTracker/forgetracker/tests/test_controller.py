from nose.tools import assert_true

from forgetracker.tests import TestController


class TestRootController(TestController):
    def test_index(self):
        response = self.app.get('/bugs/')
        assert_true('ForgeTracker for' in response)

