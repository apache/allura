from nose.tools import assert_true

from forgewiki.tests import TestController

class TestRootController(TestController):

    def test_index(self):
        response = self.app.get('/Wiki/')
        assert_true('ForgeWiki Index Page' in response)
        assert_true('ForgeWiki Index Page' in response)

    def test_index2(self):
        response = self.app.get('/Wiki/')
        assert_true('ForgeWiki Index Page' in response)
        assert_true('ForgeWiki Index Page' in response)


