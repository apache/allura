import re
import logging
from collections import defaultdict
from contextlib import contextmanager

import mock
import kombu
import pkg_resources

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
        self._exchanges = dict(
            audit=kombu.Exchange('audit'),
            react=kombu.Exchange('react'))
        self.reset()

    def reset(self):
        self._conn = self._connection_pool.acquire()
        self._channel_pool = self._conn.ChannelPool(preload=2, limit=10)

    @contextmanager
    def channel(self):
        try:
            ch = self._channel_pool.acquire()
        except kombu.exceptions.ChannelLimitExceeded:
            log.info('Channel pool exhausted, opening a new connection')
            self.reset()
            ch = self._channel_pool.acquire()
        try:
            yield ch
        finally:
            if ch.is_open: ch.release()
            else: log.info('ch is not open, not returning to pool')

    @contextmanager
    def producer(self, xn):
        with self.channel() as ch:
            prod = kombu.Producer(ch, self._exchanges[xn], auto_declare=False)
            yield prod

    def clear_exchanges(self):
        try:
            with self.channel() as ch:
                ch.exchange_delete('audit')
        except:
            pass
        try:
            with self.channel() as ch:
                ch.exchange_delete('react')
        except:
            pass

    def declare_exchanges(self):
        self.clear_exchanges()
        with self.channel() as ch:
            ch.exchange_declare('audit', 'topic', durable=True, auto_delete=False)
        with self.channel() as ch:
            ch.exchange_declare('react', 'topic', durable=True, auto_delete=False)

    def declare_queue(self, xn, qn, keys):
        try:
            with self.channel() as ch:
                ch.queue_delete(qn)
        except:
            pass
        with self.channel() as ch:
            ch.queue_declare(qn, durable=True, auto_delete=False)
        for k in keys:
            with self.channel() as ch:
                ch.queue_bind(qn, xn, k)

    def publish(self, xn, key_msgs):
       '''Publish a series of messages to an exchange using a single producer

       xn: exchange name
       key_msgs: sequence of (routing_key, message, kwargs) pairs to be published
       '''
       with self.producer(xn) as p:
           for routing_key, body, kwargs in key_msgs:
               kwargs.setdefault('serializer', 'pickle')
               p.publish(body, routing_key=routing_key, **kwargs)

class MockAMQ(object):

    def __init__(self, globals):
        self.exchanges = defaultdict(list)
        self.queue_bindings = defaultdict(list)
        self.globals = globals

    def clear(self):
        for k in self.exchanges.keys():
            self.exchanges[k][:] = []

    def create_backend(self):
        return mock.Mock()

    def publish(self, xn, routing_key, message, **kw):
        self.exchanges[xn].append(
            dict(routing_key=routing_key, message=message, kw=kw))

    def pop(self, xn):
        return self.exchanges[xn].pop(0)

    def declare_exchanges(self):
        pass

    def declare_queue(self, xn, qn, keys):
        pass

    def setup_handlers(self, paste_registry=None):
        from allura.command.reactor import tool_consumers, ReactorCommand
        from allura.command import base
        from allura import model as M
        self.queue_bindings = defaultdict(list)
        base.log = logging.getLogger('allura.command')
        base.M = M
        self.tools = []
        for ep in pkg_resources.iter_entry_points('allura'):
            try:
                self.tools.append((ep.name, ep.load()))
            except ImportError:
                base.log.warning('Canot load entry point %s', ep)
        self.reactor = ReactorCommand('reactor_setup')
        if paste_registry:
            self.reactor.registry = paste_registry
        self.reactor.globals = self.globals
        self.reactor.parse_args([])
        for name, tool in self.tools:
            for method, xn, qn, keys in tool_consumers(name, tool):
                for k in keys:
                    self.queue_bindings[xn].append(
                        dict(key=k, tool_name=name, method=method))

    def handle(self, xn):
        msg = self.pop(xn)
        for handler in self.queue_bindings[xn]:
            if self._route_matches(handler['key'], msg['routing_key']):
                self._route(xn, msg, handler['tool_name'], handler['method'])

    def handle_all(self):
        for xn, messages in self.exchanges.items():
            while messages:
                self.handle(xn)

    def _route(self, xn, msg, tool_name, method):
        if xn == 'audit':
            callback = self.reactor.route_audit(tool_name, method)
        else:
            callback = self.reactor.route_react(tool_name, method)
        data = msg['message']
        message = mock.Mock()
        message.delivery_info = dict(
            routing_key=msg['routing_key'])
        message.ack = lambda:None
        return callback(data, message)

    def _route_matches(self, pattern, key):
        re_pattern = (pattern
                      .replace('.', r'\.')
                      .replace('*', r'(?:\w+)')
                      .replace('#', r'(?:\w+)(?:\.\w+)*'))
        return re.match(re_pattern+'$', key)
