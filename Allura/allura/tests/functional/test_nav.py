import mock
import json
from tg import config
from pylons import app_globals as g

from allura.tests import TestController
from allura.lib import helpers as h


class TestNavigation(TestController):
    """
    Test left navigation in top nav.
    - Test of global_nav links.
    - Test of logo.
    """

    def setUp(self):
        super(TestNavigation, self).setUp()
        self.logo_pattern = ('div', {'class': 'nav-logo'})
        self.global_nav_pattent = ('nav', {'class': 'nav-left'})
        self.nav_data = {
            "title": "Link Test", "url": "http://example.com"}
        self.logo_data = {
            "redirect_link": "/", "image_path": "test_image.png"}
        self.config_data = {
            "global_nav": json.dumps([self.nav_data]),
            "logo": json.dumps(self.logo_data)
        }

    def test_global_nav_links_present(self):
        with h.push_config(config, **self.config_data):
            response = self.app.get('/')
        nav_left = response.html.find(*self.global_nav_pattent)
        assert len(nav_left.findAll('a')) == 1
        assert nav_left.a.get('href') == self.nav_data['url']
        assert nav_left.a.text == self.nav_data['title']

    def test_logo_absent_if_not_image_path(self):
        with h.push_config(config, **self.config_data):
            response = self.app.get('/')
        nav_logo = response.html.find(*self.logo_pattern)
        assert len(nav_logo.findAll('a')) == 0

    @mock.patch.object(g, 'nav_logo')
    def test_logo_present(self, glogo):
        response = self.app.get('/')
        nav_logo = response.html.find(*self.logo_pattern)
        assert len(nav_logo.findAll('img')) == 1
