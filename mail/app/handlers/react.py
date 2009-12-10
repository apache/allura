import logging

from lamson.routing import route, route_like, stateless
from config.settings import relay
from lamson import view, queue

#from pymongo import Connection

import os
#import sys
#import time
#from pkg_resources import iter_entry_points
#from multiprocessing import Process
#from pprint import pformat

import ming
import pylons
#from paste.script import command
from paste.deploy import appconfig
#from carrot.connection import BrokerConnection
#from carrot.messaging import Consumer

from pyforge.config.environment import load_environment

from pyforge import model as M
from pyforge.model import Project

logging.config.fileConfig("config/jtb_logging.conf")

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

#    connection = Connection('localhost', 27017)
#    db = connection['projects:' + project ]
#    collection = db['config']
#    somevalue = collection.find()
#    logging.debug('JTB(BASIC) prove logging works')
#    somevalue = Project.m.find().all()
#    somevalue = Project.m.find({"name":"test"}).one()
    try:
        somevalue = Project.m.find({"name":proj}).one()
    except:
        logging.debug('JTB(BAD) project "' + proj + '" does not exist')
    else:
        relay.deliver(message)
        logging.debug('JTB(GOOD) project "' + proj + '" exists!')


#    try:
#        somevalue
#    except NameError:
#        logging.debug('JTB(BAD) project "' + proj + '" does not exist')
##        logging.debug('JTB(BAD) project does not exist')
#
#    else:
#        relay.deliver(message)
#        logging.debug('JTB(GOOD) project "' + proj + '" exists!')
##        logging.debug('JTB(GOOD) project exists!')

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

