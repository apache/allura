# -*- coding: utf-8 -*-

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

"""The base Controller API."""
from webob import exc
import pylons
from tg import TGController

__all__ = ['WsgiDispatchController']


class WsgiDispatchController(TGController):

    """
    Base class for the controllers in the application.

    Your web application should have one of these. The root of
    your application is used to compute URLs used by your app.

    """

    def _setup_request(self):
        '''Responsible for setting all the values we need to be set on pylons.tmpl_context'''
        raise NotImplementedError, '_setup_request'

    def _cleanup_request(self):
        raise NotImplementedError, '_cleanup_request'

    def __call__(self, environ, start_response):
        try:
            self._setup_request()
            response = super(WsgiDispatchController, self).__call__(
                environ, start_response)
            return self.cleanup_iterator(response)
        except exc.HTTPException, err:
            return err(environ, start_response)

    def cleanup_iterator(self, response):
        for chunk in response:
            yield chunk
        self._cleanup_request()

    def _get_dispatchable(self, url_path):
        """Patch ``TGController._get_dispatchable`` by overriding.

        This fixes a bug in TG 2.1.5 that causes ``request.response_type``
        to not be created if ``disable_request_extensions = True`` (see
        allura/config/app_cfg.py).

        ``request.response_type`` must be set because the "trailing slash"
        decorators use it (see allura/lib/patches.py).

        This entire method can be removed if/when we upgrade to TG >= 2.2.1

        """
        pylons.request.response_type = None
        return super(WsgiDispatchController, self)._get_dispatchable(url_path)
