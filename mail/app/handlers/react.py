import logging

from lamson.routing import route, route_like, stateless
from config.settings import relay
from lamson import view, queue

import os

import ming
import pylons
from pylons import c
from paste.deploy import appconfig

from pyforge.config.environment import load_environment

from pyforge import model as M
from pyforge.model import Project
from pyforge.lib.app_globals import Globals

logging.config.fileConfig("config/react_logging.conf")

class EmptyClass(object): pass

class ProjectContents:
    def __init__(self,indict):
        self.contents = indict
    def __getattr__(self,which):
        return self.contents.get(which,None)

@route("(appmount)\\.(apploc)@(proj)\\.(host)", appmount=".*", apploc=".*", proj=".*")
@stateless
def REACTING(message, post_name=None, appmount=None, apploc=None, proj=None, host=None):
    conf = appconfig('config:%s' % 'development.ini',relative_to=os.getcwd())
    load_environment(conf.global_conf, conf.local_conf)
    pylons.c._push_object(EmptyClass())
    pylons.g._push_object(Globals())
    ming.configure(**conf)

    try:
        valid = ProjectContents(Project.m.find({"name":proj, "database":"projects:"+proj}).one())
    except:
        try:
            valid = ProjectContents(Project.m.find({"name":proj, "database":"users:"+proj}).one())
        except:
            logging.debug('REACT: project "' + proj + '" does not exist as project or user')
        else:
#            relay.deliver(message)
            logging.debug('REACT: project "' + proj + '" exists as user with _id:' + valid._id)
    else:
#        relay.deliver(message)
        logging.debug('REACT: project "' + proj + '" exists as project with _id:' + valid._id)
        try:
            c.project = Project.m.get(_id=valid._id)
        except:
            logging.debug('REACT: cannot initialize valid project')
        else:
            logging.debug('REACT: retrieved valid project with mount point:' + appmount)
            try:
                c.project.app_config(appmount)
                c.app = c.project.app_instance(appmount)
                plugin_name=c.app.config.plugin_name
            except:
                logging.debug('REACT: invalid mount point (' + appmount + ')')
            else:
                logging.debug('REACT: valid mount point (' + appmount + ') with plugin_name:' + plugin_name)

#    conn = BrokerConnection(hostname="localhost", port=5672,
#                              userid="celeryuser", password="celerypw",
#                              virtual_host="celeryvhost")
#
#    publisher = Publisher(connection=conn,
#                            exchange="forge", routing_key="mail")
#    publisher.send({"message": message}, serializer="pickle")
#    publisher.close()

    return REACTING

