import logging
from carrot.messaging import Publisher
from carrot.connection import BrokerConnection

from lamson.routing import route, route_like, stateless
from config.settings import relay
from lamson import view, queue



@route("forge-list@(host)")
#@route("(post_name)@osb\\.(host)")
@stateless
def POSTING(message, post_name=None, host=None):
    relay.deliver(message)

    conn = BrokerConnection(hostname="localhost", port=5672,
                              userid="celeryuser", password="celerypw",
                              virtual_host="celeryvhost")

    publisher = Publisher(connection=conn,
                            exchange="forge", routing_key="mail")
    publisher.send({"message": message})
    publisher.close()

    #index_q = queue.Queue("run/posts")
    #index_q.push(message)

    return POSTING

