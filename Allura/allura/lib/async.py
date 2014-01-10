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
from Queue import Queue

log = logging.getLogger(__name__)


class Connection(object):

    def __init__(self, hostname, port, userid, password, vhost):
        import kombu
        self._conn_proto = kombu.BrokerConnection(
            hostname=hostname,
            port=port,
            userid=userid,
            password=password,
            virtual_host=vhost)
        self._connection_pool = self._conn_proto.Pool(preload=1, limit=None)
        self.reset()

    def reset(self):
        self._conn = self._connection_pool.acquire()
        self.queue = self._conn.SimpleQueue('task')


class MockAMQ(object):

    def __init__(self, globals):
        self.globals = globals
        self.reset()

    def reset(self):
        self.queue = Queue()
