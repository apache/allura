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

import json
from mock import patch

from allura.lib.phone.nexmo import NexmoPhoneService


class TestPhoneService:

    def setup_method(self, method):
        config = {'phone.api_key': 'test-api-key',
                  'phone.api_secret': 'test-api-secret',
                  'site_name': 'Very loooooooooong site name'}
        self.phone = NexmoPhoneService(config)

    def test_add_common_params(self):
        params = {'number': '1234567890', 'brand': 'Allura'}
        res = self.phone.add_common_params(params)
        expected = {'number': '1234567890',
                    'brand': 'Allura',
                    'api_key': 'test-api-key',
                    'api_secret': 'test-api-secret'}
        assert expected == res

        self.phone.config['phone.lang'] = 'it-it'
        res = self.phone.add_common_params(params)
        expected['lg'] = 'it-it'
        assert expected == res

    def test_error(self):
        res = self.phone.error()
        expected = {'status': 'error',
                    'error': 'Failed sending request to Nexmo'}
        assert expected == res
        # not allowed code
        res = self.phone.error(code='2', msg='text')
        assert expected == res
        # allowed code
        res = self.phone.error(code='15', msg='text')
        expected = {'status': 'error', 'error': 'text'}
        assert expected == res

        # invalid format, possibly US
        res = self.phone.error(code='3', msg='Invalid value for parameter: number', number='8005551234')
        assert res['status'] == 'error'
        assert 'Invalid value for parameter: number' in res['error']
        assert 'country code' in res['error']
        assert 'US' in res['error']

        # invalid format, not US
        res = self.phone.error(code='3', msg='Invalid value for parameter: number', number='738005551234')
        assert res['status'] == 'error'
        assert 'Invalid value for parameter: number' in res['error']
        assert 'country code' in res['error']
        assert 'US' not in res['error']

    def test_ok(self):
        res = self.phone.ok(request_id='123', other='smth')
        expected = {'status': 'ok', 'request_id': '123', 'other': 'smth'}
        assert expected == res

    @patch('allura.lib.phone.nexmo.requests', autospec=True)
    def test_verify(self, req):
        req.post.return_value.json.return_value = {
            'request_id': 'test-req-id',
            'status': '0',
        }
        data = json.dumps({
            'number': '1234567890',
            'api_key': 'test-api-key',
            'api_secret': 'test-api-secret',
            'brand': 'Very loooooooooong',
        }, sort_keys=True)
        headers = {'Content-Type': 'application/json'}

        resp = self.phone.verify('1234567890')
        expected = {'status': 'ok', 'request_id': 'test-req-id'}
        assert expected == resp
        req.post.assert_called_once_with(
            'https://api.nexmo.com/verify/json',
            data=data,
            headers=headers)

        req.post.reset_mock()
        req.post.return_value.json.return_value = {
            'status': '3',
            'error_text': 'Something went wrong',
        }
        resp = self.phone.verify('1234567890')
        expected = {'status': 'error', 'error': 'Something went wrong'}
        assert expected == resp
        req.post.assert_called_once_with(
            'https://api.nexmo.com/verify/json',
            data=data,
            headers=headers)

    @patch('allura.lib.phone.nexmo.requests', autospec=True)
    def test_verify_exception(self, req):
        req.post.side_effect = Exception('Boom!')
        resp = self.phone.verify('1234567890')
        expected = {'status': 'error',
                    'error': 'Failed sending request to Nexmo'}
        assert expected == resp

    @patch('allura.lib.phone.nexmo.requests', autospec=True)
    def test_check(self, req):
        req.post.return_value.json.return_value = {
            'request_id': 'test-req-id',
            'status': '0',
        }
        data = json.dumps({
            'request_id': 'test-req-id',
            'code': '1234',
            'api_key': 'test-api-key',
            'api_secret': 'test-api-secret',
        }, sort_keys=True)
        headers = {'Content-Type': 'application/json'}

        resp = self.phone.check('test-req-id', '1234')
        expected = {'status': 'ok', 'request_id': 'test-req-id'}
        assert expected == resp
        req.post.assert_called_once_with(
            'https://api.nexmo.com/verify/check/json',
            data=data,
            headers=headers)

        req.post.reset_mock()
        req.post.return_value.json.return_value = {
            'status': '3',
            'error_text': 'Something went wrong',
        }
        resp = self.phone.check('test-req-id', '1234')
        expected = {'status': 'error', 'error': 'Something went wrong'}
        assert expected == resp
        req.post.assert_called_once_with(
            'https://api.nexmo.com/verify/check/json',
            data=data,
            headers=headers)

    @patch('allura.lib.phone.nexmo.requests', autospec=True)
    def test_check_exception(self, req):
        req.post.side_effect = Exception('Boom!')
        resp = self.phone.check('req-id', '1234')
        expected = {'status': 'error',
                    'error': 'Failed sending request to Nexmo'}
        assert expected == resp
