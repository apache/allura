import mock
import json
from tg import config

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

    def test_global_nav_links_present(self):
        data = {"title": "Link Test", "url": "http://example.com"}
        with h.push_config(config, **{"global_nav": json.dumps([data])}):
            response = self.app.get('/')
            assert response.html.nav('a')[0].text == \
                data['title']
            assert response.html.nav('a')[0].attrs[-1][-1] == \
                data['url']

    def test_logo_absent_if_not_image_path(self):
        data = {"redirect_link": "/", "image_path": "bad_image.png"}
        with h.push_config(config, **{"logo": json.dumps(data)}):
            response = self.app.get('/')
            self.logo = json.loads(config.get('logo'))
        main_page_link = response.html.nav('a')[0].attrs[-1][-1]
        assert main_page_link != self.logo['redirect_link']

    # @mock.patch('allura.lib.app_globals.os.path.exists')
    # def test_logo_present(self, path_exists):
    #     path_exists.return_value = True
    #     data = {"redirect_link": "/", "image_path": "user123.png"}
    #     with h.push_config(config, **{"logo": json.dumps(data)}):
    #         response = self.app.get('/')
    #         self.logo = json.loads(config.get('logo'))
    #     main_page_link = response.html.nav('a')[0].attrs[-1][-1]
    #     image_link = response.html.html.nav('a')[0].img.attrs[-1][-1]
    #     assert main_page_link == self.logo['redirect_link']
    #     assert self.logo['image_path'] in image_link

    # @mock.patch("allura.lib.app_globals.config")
    # def test_logo_redirect_url_absent_and_set_default(self, _config):
    #     _config.get('logo').return_value = str({
    #         "redirect_link": "/",
    #         "image_path": "a.png"
    #     })
    #     response = self.app.get('/')
    #     main_page_link = response.html.findAll('nav')[0]('a')[0].attrs[-1][-1]
    #     assert main_page_link == '/'
