from alluratest.controller import TestController


class TestRootController(TestController):
    def test_root(self):
        response = self.app.get('/downloads/nav.json')
        root = self.app.get('/p/test/wiki/').follow()
        nav_links = root.html.find('div', dict(id='top_nav')).findAll('a')
        assert len(nav_links) ==  len(response.json['menu'])
        for nl, entry in zip(nav_links, response.json['menu']):
            assert nl['href'] == entry['url']


