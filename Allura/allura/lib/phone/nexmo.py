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

import logging
from urlparse import urljoin

import json
import requests

log = logging.getLogger(__name__)


class NexmoPhoneService(object):
    """
    Implementation of :class:`allura.lib.phone.PhoneService` interface
    for Nexmo Verify

    To enable NexmoPhoneService in your Allura instance, first enable the entry
    point in setup.py::

        [allura.phone]
        nexmo = allura.lib.phone.nexmo:NexmoPhoneService

    Then include the following parameters in your .ini file::

        phone.method = nexmo
        phone.api_key = <your Nexmo API key here>
        phone.api_secret = <your Nexmo API secret here>
    """

    BASE_URL = 'https://api.nexmo.com/'

    def __init__(self, config):
        self.config = config
        self.api_key = config.get('phone.api_key')
        self.api_secret = config.get('phone.api_secret')

    def add_common_params(self, params):
        common = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
        }
        return dict(params, **common)

    def error(self, msg):
        return {'status': 'error', 'error': msg}

    def ok(self, **params):
        return dict({'status': 'ok'}, **params)

    def post(self, url, **params):
        if url[-1] != '/':
            url += '/'
        url = urljoin(url, 'json')
        headers = {'Content-Type': 'application/json'}
        params = json.dumps(self.add_common_params(params))
        log.info('PhoneService (nexmo) request: %s %s', url, params)
        try:
            resp = requests.post(url, data=params, headers=headers)
            log.info('PhoneService (nexmo) response: %s', resp.content)
            resp = resp.json()
        except Exception:
            msg = 'Failed sending request to Nexmo'
            log.exception(msg)
            return self.error(msg)
        if resp.get('status') == '0':
            return self.ok(request_id=resp.get('request_id'))
        return self.error(resp.get('error_text'))

    def verify(self, number):
        url = urljoin(self.BASE_URL, 'verify')
        # Required. Brand or name of your app, service the verification is
        # for. This alphanumeric (maximum length 18 characters) will be
        # used inside the body of all SMS and TTS messages sent (e.g. "Your
        # <brand> PIN code is ..")
        brand = self.config.get('site_name')[:18]
        return self.post(url, number=number, brand=brand)

    def check(self, request_id, pin):
        url = urljoin(self.BASE_URL, 'verify/check')
        return self.post(url, request_id=request_id, code=pin)
