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

import unittest
from calendar import timegm
from datetime import datetime

import bson
import mock

from allura.lib import zarkov_helpers as zh


class TestZarkovClient(unittest.TestCase):

    def setUp(self):
        addr = 'tcp://0.0.0.0:0'
        ctx = mock.Mock()
        self.socket = mock.Mock()
        ctx.socket = mock.Mock(return_value=self.socket)
        PUSH = mock.Mock()
        with mock.patch('allura.lib.zarkov_helpers.zmq') as zmq:
            zmq.PUSH = PUSH
            zmq.Context.instance.return_value = ctx
            self.client = zh.ZarkovClient(addr)
        zmq.Context.instance.assert_called_once_with()
        ctx.socket.assert_called_once_with(PUSH)
        self.socket.connect.assert_called_once_with(addr)

    def test_event(self):
        self.client.event('test', dict(user='testuser'))
        obj = bson.BSON.encode(dict(
            type='test',
            context=dict(user='testuser'),
            extra=None))
        self.socket.send.assert_called_once_with(obj)

