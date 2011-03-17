import logging
from Queue import Queue

import kombu

log = logging.getLogger(__name__)

class Connection(object):

    def __init__(self, hostname, port, userid, password, vhost):
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
