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
from __future__ import unicode_literals
from __future__ import absolute_import
from tg import TGController

__all__ = ['WsgiDispatchController']


class WsgiDispatchController(TGController):

    """
    Base class for the controllers in the application.

    Your web application should have one of these. The root of
    your application is used to compute URLs used by your app.

    """

    def _setup_request(self):
        '''Responsible for setting all the values we need to be set on tg.tmpl_context'''
        raise NotImplementedError('_setup_request')

    def _perform_call(self, context):
        self._setup_request()
        return super(WsgiDispatchController, self)._perform_call(context)
