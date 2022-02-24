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

from formencode import validators as fev
import requests

from allura.lib import validators


class TracURLValidator(validators.URLIsPrivate):
    not_empty = True
    messages = {
        'unavailable': 'This project is unavailable for import'
    }

    def _to_python(self, value, state=None):
        value = super()._to_python(value, state)
        # remove extraneous /wiki/[PageName] from the end of the URL
        url_parts = value.split('/')
        try:
            wiki_in_url = url_parts.index('wiki')
        except ValueError:
            wiki_in_url = -1
        if wiki_in_url >= len(url_parts) - 2:
            value = '/'.join(url_parts[:wiki_in_url])
        # normalize trailing slash
        value = value.rstrip('/') + '/'

        try:
            resp = requests.head(value, allow_redirects=True, timeout=10)
        except OSError:
            # fall through to 'raise' below
            pass
        else:
            if resp.status_code == 200:
                return value
        raise fev.Invalid(self.message('unavailable', state), value, state)
