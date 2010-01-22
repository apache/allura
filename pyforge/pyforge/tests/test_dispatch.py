from pyforge.tests import TestController

app = None

class TestDispatch(TestController):

    def test_dispatch(self):
        r = self.app.get('/dispatch/foo/')
        assert r.body == 'index foo', r
        r = self.app.get('/dispatch/foo/bar')
        assert r.body ==  "default(foo)(('bar',))", r
        self.app.get('/not_found', status=404)
        self.app.get('/dispatch/', status=404)
        self.app.get('/hello/foo/bar', status=404)



