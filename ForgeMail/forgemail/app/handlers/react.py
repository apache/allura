import logging
logging.config.fileConfig("config/react_logging.conf")

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


class EmptyClass(object): pass

@route("(appmount)\\.(apploc)@(proj)\\.(host)", appmount=".*", apploc=".*", proj=".*")
@stateless
def REACTING(message, post_name=None, appmount=None, apploc=None, proj=None, host=None):
    conf = appconfig('config:%s' % '../pyforge/development.ini',relative_to=os.getcwd())
    load_environment(conf.global_conf, conf.local_conf)
    pylons.c._push_object(EmptyClass())
    pylons.g._push_object(Globals())
    ming.configure(**conf)

    project_id = '/'.join(reversed(proj.split('.'))) + '/'
    try:
        valid = M.Project.query.get(_id=project_id)
    except:
        logging.debug('REACT: project "' + proj + '" does not exist as project or user')
    else:
        logging.debug('REACT: project "' + proj + '" exists with id:' + project_id)
        try:
            c.project = M.Project.query.get(_id=project_id)
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
                routing_key = plugin_name + '.' + apploc
                mailto = message.__getitem__('To')
                mailfrom = message.__getitem__('From')
                mailsubj = message.__getitem__('Subject')
                mailbody = message.body()
                logging.debug('REACT: *** TO *** = ' + mailto)
                logging.debug('REACT: *** FROM *** = ' + mailfrom)
                logging.debug('REACT: *** SUBJECT *** = ' + mailsubj)
                logging.debug('REACT: *** CONTENT *** = ' + message.body())
                try:
                    pylons.g.publish('audit', routing_key,
                        dict(to=mailto,fro=mailfrom,subject=mailsubj,body=mailbody),
                        serializer='yaml')
                except:
                    logging.debug('REACT: unable to queue message in carrot')
                else:
                    logging.debug('REACT: successfully queued message in carrot with key:' + routing_key)

    return REACTING

