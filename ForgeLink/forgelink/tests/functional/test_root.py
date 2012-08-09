from allura.tests import decorators as td
from alluratest.controller import TestController


class TestRootController(TestController):
    def test_root_index_no_url(self):
        response = self.app.get('/link/index')
        assert 'Link is not configured' in response

    @td.with_link
    def test_root_index_with_url(self):
        response = self.app.get('/admin/link/options', validate_chunk=True)
        response.form['url'] = 'http://www.google.com/'
        response.form.submit()
        redirected = self.app.get('/link/index').follow()
        assert redirected.request.url == 'http://www.google.com/'

    @td.with_link
    def test_root_with_url(self):
        response = self.app.get('/admin/link/options', validate_chunk=True)
        response.form['url'] = 'http://www.google.com/'
        response.form.submit()
        redirected = self.app.get('/link').follow()
        assert redirected.request.url == 'http://www.google.com/'

    @td.with_link
    def test_root_suffix_with_url_slash(self):
        response = self.app.get('/admin/link/options', validate_chunk=True)
        response.form['url'] = 'http://www.google.com/'
        response.form.submit()
        redirected = self.app.get('/link/service')
        # HACK: support for remote redirects is limited in follow()
        assert 'http://www.google.com/service' in redirected

    @td.with_link
    def test_root_suffix_with_url_value(self):
        response = self.app.get('/admin/link/options', validate_chunk=True)
        response.form['url'] = 'http://www.google.de/search?q='
        response.form.submit()
        response = self.app.get('/link/help')
        # HACK: support for remote redirects is limited in follow()
        assert 'http://www.google.de/search?q=help' in response

