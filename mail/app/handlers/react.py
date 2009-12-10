import logging

from lamson.routing import route, route_like, stateless
from config.settings import relay
from lamson import view, queue

import os

import ming
import pylons
from paste.deploy import appconfig

from pyforge.config.environment import load_environment

from pyforge import model as M
from pyforge.model import Project

logging.config.fileConfig("config/react_logging.conf")

class EmptyClass(object): pass

@route("(loc)@(proj)\\.(host)", loc=".*", proj=".*")
@stateless
def REACTING(message, post_name=None, loc=None, proj=None, host=None):
    conf = appconfig('config:%s' % 'development.ini',relative_to=os.getcwd())
    load_environment(conf.global_conf, conf.local_conf)
    pylons.c._push_object(EmptyClass())
    from pyforge.lib.app_globals import Globals
    pylons.g._push_object(Globals())
    ming.configure(**conf)

    try:
        valid = Project.m.find({"name":proj, "database":"projects:"+proj}).one()
    except:
        try:
            valid = Project.m.find({"name":proj, "database":"users:"+proj}).one()
        except:
            logging.debug('REACT: project "' + proj + '" does not exist as project or user')
        else:
            relay.deliver(message)
            logging.debug('REACT: project "' + proj + '" exists as user!')
    else:
        relay.deliver(message)
        logging.debug('REACT: project "' + proj + '" exists as project!')


#    conn = BrokerConnection(hostname="localhost", port=5672,
#                              userid="celeryuser", password="celerypw",
#                              virtual_host="celeryvhost")
#
#    publisher = Publisher(connection=conn,
#                            exchange="forge", routing_key="mail")
#    publisher.send({"message": message}, serializer="pickle")
#    publisher.close()
#
#    #index_q = queue.Queue("run/posts")
#    #index_q.push(message)

    return REACTING

