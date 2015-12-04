import mock
import json
from tg import config
from pylons import app_globals as g

from allura.tests import TestController
from allura.lib import helpers as h


class TestNavigation(TestController):
    """
    Test div-logo and nav-left:
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

    def tearDown(self):
        g._Globals__shared_state.pop('global_nav', None)
        g._Globals__shared_state.pop('nav_logo', None)

    def _set_config(self):
        return {
            "global_nav": json.dumps([self.nav_data]),
            "logo": json.dumps(self.logo_data)
        }

    def test_global_nav_links_present(self):
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/')
        nav_left = response.html.find(*self.global_nav_pattent)
        assert len(nav_left.findAll('a')) == 1
        assert nav_left.a.get('href') == self.nav_data['url']
        assert nav_left.a.text == self.nav_data['title']

    @mock.patch.object(g, 'global_nav', return_value=[])
    def test_global_nav_links_absent(self, global_nav):
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/')
        nav_left = response.html.find(*self.global_nav_pattent)
        assert len(nav_left.findAll('a')) == 0

    def test_logo_absent_if_not_image_path(self):
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/')
        nav_logo = response.html.find(*self.logo_pattern)
        assert len(nav_logo.findAll('a')) == 0

    def test_logo_present(self):
        self.logo_data = {
            "redirect_link": "/", "image_path": "user.png"}
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/')
        nav_logo = response.html.find(*self.logo_pattern)
        assert len(nav_logo.findAll('a')) == 1
        assert self.logo_data['image_path'] in nav_logo.a.img.get('src')

    def test_logo_no_redirect_url_set_default(self):
        self.logo_data = {
            "redirect_link": "", "image_path": "user.png"}
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/')
        nav_logo = response.html.find(*self.logo_pattern)
        assert len(nav_logo.findAll('a')) == 1
        assert nav_logo.a.get('href') == '/'
