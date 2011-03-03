from contextlib import contextmanager

import kombu

class Connection(object):

    def __init__(self, hostname, port, userid, password, vhost):
        self._conn = kombu.BrokerConnection(
            hostname=hostname,
            port=port,
            userid=userid,
            password=password,
            virtual_host=vhost)
        self._channel_pool = self._conn.ChannelPool(limit=10)
        self._exchanges = dict(
            audit=kombu.Exchange('audit'),
            react=kombu.Exchange('react'))

    @contextmanager
    def channel(self):
        ch = self._channel_pool.acquire()
        try:
            yield ch
        finally:
            ch.release()

    @contextmanager
    def producer(self, xn):
        with self.channel() as ch:
            prod = kombu.Producer(ch, self._exchanges[xn], auto_declare=False)
            yield prod

    def declare_exchanges(self):
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
        with self.channel() as ch:
            ch.exchange_declare('audit', 'topic', durable=True, auto_delete=False)
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
