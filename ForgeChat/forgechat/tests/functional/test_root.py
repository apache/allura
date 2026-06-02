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
from datetime import datetime

from bson import ObjectId
from tg import tmpl_context as c
from ming.odm import ThreadLocalODMSession

from alluratest.controller import TestController
from allura.tests.decorators import with_tool
from allura.lib import helpers as h
from allura import model as M

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
                '_csrf_token': self.app.cookies['_csrf_token']}
        ch = CM.ChatChannel.query.get()
        assert ch.channel == ''
        resp = self.app.post('/p/test/admin/chat/configure', data)
        expected = {'status': 'ok', 'message': 'Chat options updated'}
        assert json.loads(self.webflash(resp)) == expected
        ch = CM.ChatChannel.query.get()
        assert ch.channel == 'test channel'

    @with_chat
    def test_chat_tool_read_required(self):
        day_url = '/p/test/chat/2020/01/03/'
        # baseline: anon can read the chat tool on a public project
        assert self.app.get(day_url, extra_environ={'username': '*anonymous'},
                            status=200)
        # remove the chat tool's own 'read' for anon & authenticated (project read unchanged)
        with h.push_context('test', 'chat', neighborhood='Projects'):
            role = M.ProjectRole.by_name('*anonymous')._id
            read_permission = M.ACE.allow(role, 'read')
            c.app.config.acl.remove(read_permission)
        ThreadLocalODMSession.flush_all()
        # anon is now blocked from the chat tool even though it still has project read
        self.app.get(day_url, extra_environ={'username': '*anonymous'}, status=302)
        # a project admin still has read
        assert self.app.get(day_url, status=200)

    @with_chat
    def test_day_messages_scoped_to_chat_instance(self):
        ts = datetime(2020, 1, 2, 12, 0)
        h.set_context('test', 'chat', neighborhood='Projects')
        # message belonging to THIS chat instance
        CM.ChatMessage(sender='alice', channel='#a', text='message-alpha', timestamp=ts)
        # message belonging to a DIFFERENT chat instance (other app_config_id, same project db)
        CM.ChatMessage(app_config_id=ObjectId(), sender='bob', channel='#b',
                       text='message-bravo', timestamp=ts)
        ThreadLocalODMSession.flush_all()
        # the day view must show only this instance's message
        r = self.app.get('/p/test/chat/2020/01/02/')
        assert 'message-alpha' in r
        assert 'message-bravo' not in r
