import logging
from lamson.routing import route, route_like, stateless
from config.settings import relay
from lamson import view, queue

@route("forge-list@(host)")
#@route("(post_name)@osb\\.(host)")
@stateless
def POSTING(message, post_name=None, host=None):
    relay.deliver(message)

    # drop the message off into the 'posts' queue for later
    index_q = queue.Queue("run/posts")
    index_q.push(message)

    return POSTING

