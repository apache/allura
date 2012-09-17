from allura.tests import decorators as td
from alluratest.controller import TestController


class TestRootController(TestController):
    def setUp(self):
        super(TestRootController, self).setUp()
        self.setup_with_tools()

    @td.with_url
    def setup_with_tools(self):
        pass

    def test_shorturl_add(self):
        response = self.app.get('/admin/url/add')
        response.form['short_url'] = 'test'
        response.form['full_url'] = 'http://www.google.com/'
        response.form.submit()
        redirected = self.app.get('/url/test').follow()
        assert redirected.request.url == 'http://www.google.com/'

    def test_shorturl_not_found(self):
        self.app.post('/admin/url/add',
                      dict(short_url='test',
                           full_url='http://www.google.com/',
                           description="description2"))
        r = self.app.get('/url/test2', status=404)
        r = self.app.get('/url/')
        assert 'http://www.google.com/' in r

    def test_shorturl_private(self):
        self.app.post('/admin/url/add',
                      dict(short_url='test_private',
                           full_url='http://www.amazone.com/',
                           private='on',
                           description="description1"))
        r = self.app.get('/url/')
        assert 'http://www.amazone.com/' in r
        assert '<td><small>yes</small></td>' in r

    def test_shorturl_errors(self):
        d = dict(short_url='http://www.amazone.com/',
                 full_url='http://www.amazone.com/')
        r = self.app.post('/admin/url/add', params=d)
        assert 'error' in self.webflash(r)
        d = dict(short_url='http://www.amazone.com/', full_url='amazone')
        r = self.app.post('/admin/url/add', params=d)
        assert 'error' in self.webflash(r)
