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

from mock import MagicMock, patch
from allura.lib.custom_middleware import CORSMiddleware


class TestCORSMiddleware:

    def setup_method(self, method):
        self.app = MagicMock()
        self.allowed_methods = ['GET', 'POST', 'DELETE']
        self.allowed_headers = ['Authorization', 'Accept']
        self.cors = CORSMiddleware(
            self.app,
            self.allowed_methods,
            self.allowed_headers)

    def test_init(self):
        cors = CORSMiddleware(self.app, ['get', 'post'], ['Some-Header'])
        assert cors.app == self.app
        assert cors.allowed_methods == ['GET', 'POST']
        assert cors.allowed_headers == {'some-header'}

    def test_call_not_api_request(self):
        callback = MagicMock()
        env = {'PATH_INFO': '/p/test/'}
        self.cors(env, callback)
        self.app.assert_called_once_with(env, callback)

    def test_call_invalid_cors(self):
        callback = MagicMock()
        env = {'PATH_INFO': '/rest/p/test/'}
        self.cors(env, callback)
        self.app.assert_called_once_with(env, callback)

    def test_handle_call_simple_request(self):
        callback = MagicMock()
        env = {'PATH_INFO': '/rest/p/test/',
               'HTTP_ORIGIN': 'my.site.com',
               'REQUEST_METHOD': 'GET'}
        self.cors(env, callback)
        assert self.app.call_count == 1
        assert self.app.call_args_list[0][0][0] == env
        assert self.app.call_args_list[0][0][1] != callback

    @patch('allura.lib.custom_middleware.exc', autospec=True)
    def test_handle_call_preflight_request(self, exc):
        callback = MagicMock()
        env = {'PATH_INFO': '/rest/p/test/',
               'HTTP_ORIGIN': 'my.site.com',
               'REQUEST_METHOD': 'OPTIONS',
               'HTTP_ACCESS_CONTROL_REQUEST_METHOD': 'POST'}
        self.cors(env, callback)
        assert self.app.call_count == 0
        exc.HTTPOk.assert_called_once_with(headers=[
            ('Access-Control-Allow-Origin', '*'),
            ('Access-Control-Allow-Methods', 'GET, POST, DELETE'),
            ('Access-Control-Allow-Headers', 'accept, authorization')
        ])
        exc.HTTPOk.return_value.assert_called_once_with(env, callback)

    def test_get_response_headers_simple(self):
        # Allow-Origin: * is crucial for security, since that prevents browsers from exposing results fetched withCredentials: true (aka cookies)
        assert (self.cors.get_response_headers() ==
                     [('Access-Control-Allow-Origin', '*')])
        assert (self.cors.get_response_headers(preflight=False) ==
                     [('Access-Control-Allow-Origin', '*')])

    def test_get_response_headers_preflight(self):
        assert (
            self.cors.get_response_headers(preflight=True) ==
            [('Access-Control-Allow-Origin', '*'),
             ('Access-Control-Allow-Methods', 'GET, POST, DELETE'),
             ('Access-Control-Allow-Headers', 'accept, authorization')])

    def test_get_response_headers_preflight_with_cache(self):
        cors = CORSMiddleware(self.app, ['GET', 'PUT'], ['Accept'], 86400)
        assert (cors.get_response_headers(preflight=True) ==
                     [('Access-Control-Allow-Origin', '*'),
                      ('Access-Control-Allow-Methods', 'GET, PUT'),
                      ('Access-Control-Allow-Headers', 'accept'),
                      ('Access-Control-Max-Age', '86400')])

    def test_get_access_control_request_headers(self):
        key = 'HTTP_ACCESS_CONTROL_REQUEST_HEADERS'
        f = self.cors.get_access_control_request_headers
        assert f({}) == set()
        assert f({key: ''}) == set()
        assert (f({key: 'Authorization, Accept'}) ==
                     {'authorization', 'accept'})
