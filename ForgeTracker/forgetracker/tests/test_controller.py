from nose.tools import assert_true

from alluratest.controller import TestController


class TestRootController(TestController):
    def test_index(self):
        response = self.app.get('/bugs/')
        assert_true('bugs' in response)

