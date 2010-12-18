from alluratest.controller import TestController


class TestRootController(TestController):

    def test_root_index(self):
        response = self.app.get('/chat/').follow()
        assert 'Log for' in response
