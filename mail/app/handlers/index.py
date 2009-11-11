from lamson import queue
from lamson.routing import route, stateless
import logging

@route("(post_name)@osb\\.(host)")
@stateless
def START(message, post_name=None, host=None):
    logging.debug("Got message from %s", message['from'])

