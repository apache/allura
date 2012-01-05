from nose.tools import assert_true

from allura.tests import decorators as td
from alluratest.controller import TestController


class TestRootController(TestController):
    @td.with_tracker
    def test_index(self):
        response = self.app.get('/bugs/')
        assert_true('bugs' in response)

