from allura.tests import TestController

class TestSearch(TestController):

    def test_global_search_controller(self):
        self.app.get('/gsearch/')
        self.app.get('/gsearch/', params=dict(q='Root'))

    def test_project_search_controller(self):
        self.app.get('/search/')
        self.app.get('/search/', params=dict(q='Root'))

