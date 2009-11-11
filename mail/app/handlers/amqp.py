import logging
from lamson.routing import route, route_like, stateless
from config.settings import relay
from lamson import view


@route("(address)@(host)", address=".+")
def START(message, address=None, host=None):
    return NEW_USER


@route_like(START)
def NEW_USER(message, address=None, host=None):
    return NEW_USER


@route_like(START)
def END(message, address=None, host=None):
    return NEW_USER(message, address, host)


@route_like(START)
@stateless
def FORWARD(message, address=None, host=None):
    relay.deliver(message)

@route("(post_name)@osb\\.(host)")
def POSTING(message, post_name=None, host=None):
    # do the regular posting to blog thing
    name, address = parseaddr(message['from'])
    post.post(post_name, address, message)
    msg = view.respond('page_ready.msg', locals())
    relay.deliver(msg)

    # drop the message off into the 'posts' queue for later
    index_q = queue.Queue("run/posts")
    index_q.push(message)

    return POSTING
