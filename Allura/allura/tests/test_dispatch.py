from allura.tests import TestController

app = None

class TestDispatch(TestController):

    validate_skip = True

    def test_dispatch(self):
        r = self.app.get('/dispatch/foo/')
        assert r.body == 'index foo', r
        self.app.get('/not_found', status=404)
        self.app.get('/dispatch/', status=404)
        # self.app.get('/hello/foo/bar', status=404)



