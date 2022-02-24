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

"""Error controller"""

from tg import request, expose

__all__ = ['ErrorController']


class ErrorController:

    @expose('jinja:allura:templates/error.html')
    def document(self, *args, **kwargs):
        """Render the error document"""
        resp = request.environ.get('tg.original_response')
        code = -1
        if resp:
            code = resp.status_int
        default_message = ("<p>We're sorry but we weren't able to process "
                           " this request.</p>")
        message = request.environ.get('error_message', default_message)
        message += '<pre>%r</pre>' % resp
        return dict(code=code, message=message)
