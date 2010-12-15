from allura.tests import TestController
from alluratest.validation import validate_page


class TestSearch(TestController):

    def test_global_search_controller(self):
        r = self.app.get('/gsearch/')
        validate_page(r)
        r = self.app.get('/gsearch/', params=dict(q='Root'))
        validate_page(r)

    def test_project_search_controller(self):
        r = self.app.get('/search/')
        validate_page(r)
        r = self.app.get('/search/', params=dict(q='Root'))
        validate_page(r)

