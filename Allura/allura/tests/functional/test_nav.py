#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import mock
import json
from tg import config
from tg import app_globals as g

from allura.tests import TestController
from allura.lib import helpers as h


class TestNavigation(TestController):
    """
    Test div-logo and nav-left:
    - Test of global_nav links.
    - Test of logo.
    """

    def setup_method(self, method):
        super().setup_method(method)
        self.logo_pattern = ('div', {'class': 'nav-logo'})
        self.global_nav_pattern = ('nav', {'class': 'nav-left'})
        self.nav_data = {
            "title": "Link Test", "url": "http://example.com"}
        self.logo_data = {
            "link": "/", "path": "test_image.png"}
        self.width = 'width: %spx;'
        self.height = 'height: %spx;'
        g._Globals__shared_state.pop('global_nav', None)
        g._Globals__shared_state.pop('nav_logo', None)

    def _set_config(self):
        return {
            "global_nav": json.dumps([self.nav_data]),
            "logo.link": self.logo_data['link'],
            "logo.path": self.logo_data['path'],
            "logo.width": self.logo_data.get('width', ''),
            "logo.height": self.logo_data.get('height', '')
        }

    def test_global_nav_links_present(self):
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/').follow()
        nav_left = response.html.find(*self.global_nav_pattern)
        assert len(nav_left.findAll('a')) == 1
        assert nav_left.a.get('href') == self.nav_data['url']
        assert nav_left.a.text == self.nav_data['title']

    @mock.patch.object(g, 'global_nav', return_value=[])
    def test_global_nav_links_absent(self, global_nav):
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/').follow()
        nav_left = response.html.find(*self.global_nav_pattern)
        assert len(nav_left.findAll('a')) == 0

    def test_logo_absent_if_not_image_path(self):
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/').follow()
        nav_logo = response.html.find(*self.logo_pattern)
        assert len(nav_logo.findAll('a')) == 0

    def test_logo_present(self):
        self.logo_data = {
            "link": "/", "path": "user.png"}
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/').follow()
        nav_logo = response.html.find(*self.logo_pattern)
        assert len(nav_logo.findAll('a')) == 1
        assert self.logo_data['path'] in nav_logo.a.img.get('src')

    def test_logo_no_redirect_url_set_default(self):
        self.logo_data = {
            "link": "", "path": "user.png"}
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/').follow()
        nav_logo = response.html.find(*self.logo_pattern)
        assert len(nav_logo.findAll('a')) == 1
        assert nav_logo.a.get('href') == '/'

    def test_logo_image_width_and_height(self):
        self.logo_data = {
            "link": "", "path": "user.png",
            "width": 20, "height": 20}
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/').follow()
        nav_logo = response.html.find(*self.logo_pattern)
        width = self.width % self.logo_data["width"]
        height = self.height % self.logo_data["height"]
        assert nav_logo.find(
            'img', style=f'{width} {height}') is not None

    def test_missing_logo_width(self):
        self.logo_data = {
            "link": "", "path": "user.png",
            "height": 20}
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/').follow()
        nav_logo = response.html.find(*self.logo_pattern)
        height = self.height % self.logo_data["height"]
        assert nav_logo.find(
            'img', style=' %s' % height) is not None

    def test_missing_logo_height(self):
        self.logo_data = {
            "link": "/", "path": "user.png",
            "width": 20}
        with h.push_config(config, **self._set_config()):
            response = self.app.get('/').follow()
        nav_logo = response.html.find(*self.logo_pattern)
        width = self.width % self.logo_data["width"]
        assert nav_logo.find(
            'img', style='%s ' % width) is not None
