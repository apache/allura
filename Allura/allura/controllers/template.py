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

"""Fallback controller."""

from pylons.controllers.util import abort

from allura.lib.base import WsgiDispatchController

__all__ = ['TemplateController']


class TemplateController(WsgiDispatchController):

    """
    The fallback controller for allura.
    
    By default, the final controller tried to fulfill the request
    when no other routes match. It may be used to display a template
    when all else fails, e.g.::
    
        def view(self, url):
            return render('/%s' % url)
    
    Or if you're using Mako and want to explicitly send a 404 (Not
    Found) response code when the requested template doesn't exist::
    
        import mako.exceptions
        
        def view(self, url):
            try:
                return render('/%s' % url)
            except mako.exceptions.TopLevelLookupException:
                abort(404)
    
    """

    def view(self, url):
        """Abort the request with a 404 HTTP status code."""
        abort(404)
