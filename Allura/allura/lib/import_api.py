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

from __future__ import unicode_literals
from __future__ import absolute_import
import six.moves.urllib.request, six.moves.urllib.parse, six.moves.urllib.error
import six.moves.urllib.request, six.moves.urllib.error, six.moves.urllib.parse
import six.moves.urllib.parse
import hmac
import hashlib
import json
import logging
from datetime import datetime

log = logging.getLogger(__name__)


class AlluraImportApiClient(object):

    def __init__(self, base_url, token, verbose=False, retry=True):
        self.base_url = base_url
        self.token = token
        self.verbose = verbose
        self.retry = retry

    def sign(self, path, params):
        params.append(('access_token', self.token))
        return params

    def call(self, url, **params):
        url = six.moves.urllib.parse.urljoin(self.base_url, url)
        if self.verbose:
            log.info("Import API URL: %s", url)

        params = self.sign(six.moves.urllib.parse.urlparse(url).path, list(params.items()))

        while True:
            try:
                result = six.moves.urllib.request.urlopen(url, six.moves.urllib.parse.urlencode(params))
                resp = result.read()
                return json.loads(resp)
            except six.moves.urllib.error.HTTPError as e:
                e.msg += ' ({0})'.format(url)
                if self.verbose:
                    error_content = e.read()
                    e.msg += '. Error response:\n' + error_content
                raise e
            except (six.moves.urllib.error.URLError, IOError):
                if self.retry:
                    log.exception('Error making API request, will retry')
                    continue
                raise
