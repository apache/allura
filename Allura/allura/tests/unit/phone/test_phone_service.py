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

from allura.lib.phone import PhoneService


class MockPhoneService(PhoneService):

    def verify(*args, **kw):
        return {'status': 'ok', 'request_id': 'test-request'}

    def check(*args, **kw):
        return {'status': 'ok'}


class TestPhoneService:

    def test_verify(self):
        res = PhoneService({}).verify('1234567890')
        expected = {'status': 'error',
                    'error': 'Phone service is not configured'}
        assert res == expected

    def test_check(self):
        res = PhoneService({}).check('test-req-id', '1111')
        expected = {'status': 'error',
                    'error': 'Phone service is not configured'}
        assert res == expected

    def test_get_default(self):
        config = {}
        entry_points = None
        phone = PhoneService.get(config, entry_points)
        assert isinstance(phone, PhoneService)

    def test_get_method(self):
        config = {'phone.method': 'mock'}
        entry_points = {'mock': MockPhoneService}
        phone = PhoneService.get(config, entry_points)
        assert isinstance(phone, MockPhoneService)
