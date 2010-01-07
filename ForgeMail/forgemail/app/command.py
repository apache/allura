import os
import sys
import time
import json
import logging
from pkg_resources import iter_entry_points
from multiprocessing import Process
from pprint import pformat

import ming
import pylons
from paste.script import command
from paste.deploy import appconfig
from carrot.connection import BrokerConnection
from carrot.messaging import Consumer, ConsumerSet

from pyforge.config.environment import load_environment
from pyforge.command import Command

log=None
M=None

class Command(command.Command):
    min_args = max_args = 1
    usage = 'NAME <ini file>'
    group_name = 'PyForge'

    def basic_setup(self):
        global log, M
        conf = appconfig('config:%s' % self.args[0],relative_to=os.getcwd())
        logging.config.fileConfig(self.args[0])
        from pyforge import model
        M=model
        log = logging.getLogger(__name__)
        log.info('Initialize reactor with config %r', self.args[0])
        load_environment(conf.global_conf, conf.local_conf)
        pylons.c._push_object(EmptyClass())
        from pyforge.lib.app_globals import Globals
        pylons.g._push_object(Globals())
        ming.configure(**conf)
        self.plugins = [
            (ep.name, ep.load()) for ep in iter_entry_points('pyforge') ]
        log.info('Loaded plugins')

