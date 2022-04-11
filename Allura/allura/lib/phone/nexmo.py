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
from six.moves.urllib.parse import urljoin
import cgi
import json

import requests
import jinja2
import markupsafe

from allura.lib.phone import PhoneService
from allura.lib.utils import phone_number_hash

log = logging.getLogger(__name__)


class NexmoPhoneService(PhoneService):
    """
    Implementation of :class:`allura.lib.phone.PhoneService` interface
    for Nexmo Verify
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
        if self.config.get('phone.lang'):
            common['lg'] = self.config['phone.lang']
        return dict(params, **common)

    def error(self, code=None, msg=None, number=''):
        allowed_codes = ['3', '10', '15', '16', '17']  # https://docs.nexmo.com/index.php/verify/search#verify_return_code
        if code is None or str(code) not in allowed_codes:
            msg = 'Failed sending request to Nexmo'
        if str(code) == '3' and msg.endswith(' number'):
            msg = markupsafe.Markup(
                '{}{}{}'.format(
                    cgi.escape(msg),  # escape it just in case Nexmo sent some HTML we don't want through
                    '<br>Make sure you include the country code (see examples above)',
                    '. For US numbers, you must include <code>1-</code> before the area code.' if len(number) == 10 else '',
                ))

        return {'status': 'error', 'error': msg}

    def ok(self, **params):
        return dict({'status': 'ok'}, **params)

    def post(self, url, **params):
        if url[-1] != '/':
            url += '/'
        url = urljoin(url, 'json')
        headers = {'Content-Type': 'application/json'}
        params = self.add_common_params(params)
        log_params = dict(params, api_key='...', api_secret='...')
        if 'number' in log_params:
            log_params['number'] = phone_number_hash(log_params['number'])
        post_params = json.dumps(params, sort_keys=True)
        log.info('PhoneService (nexmo) request: %s %s', url, log_params)
        try:
            resp = requests.post(url, data=post_params, headers=headers)
            log.info('PhoneService (nexmo) response: %s', resp.content)
            resp = resp.json()
        except Exception:
            log.exception('Failed sending request to Nexmo')
            return self.error()
        if resp.get('status') == '0':
            return self.ok(request_id=resp.get('request_id'))
        return self.error(code=resp.get('status'), msg=resp.get('error_text'), number=params.get('number',''))

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
