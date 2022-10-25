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

from alluratest.controller import TestController
from allura.tests.decorators import with_tool

from forgechat import model as CM


with_chat = with_tool('test', 'Chat', 'chat', 'Chat')


class TestRootController(TestController):

    def test_root_index(self):
        response = self.app.get('/chat/').follow()
        assert 'Log for' in response

    @with_chat
    def test_admin_configure(self):
        self.app.get('/').follow()  # establish session
        data = {'channel': 'test channel',
                '_session_id': self.app.cookies['_session_id']}
        ch = CM.ChatChannel.query.get()
        assert ch.channel == ''
        resp = self.app.post('/p/test/admin/chat/configure', data)
        expected = {'status': 'ok', 'message': 'Chat options updated'}
        assert json.loads(self.webflash(resp)) == expected
        ch = CM.ChatChannel.query.get()
        assert ch.channel == 'test channel'
