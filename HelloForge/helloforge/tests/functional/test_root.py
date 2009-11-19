from nose.tools import assert_true

from helloforge.tests import TestController

class TestRootController(TestController):

    def test_index(self):
        response = self.app.get('/hello_forge/')
        assert_true('HelloForge Index Page' in response)
        assert_true('HelloForge Index Page' in response)
        
    def test_index2(self):
        response = self.app.get('/hello_forge/')
        assert_true('HelloForge Index Page' in response)
        assert_true('HelloForge Index Page' in response)
        
        

