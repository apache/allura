import os
import sys
import logging
from pkg_resources import iter_entry_points

import pylons
from paste.script import command
from paste.deploy import appconfig

import ming
from pyforge.config.environment import load_environment

class EmptyClass(object): pass

class Command(command.Command):
    min_args = max_args = 1
    usage = 'NAME <ini file>'
    group_name = 'PyForge'

    def basic_setup(self):
        global log, M
        conf = appconfig('config:%s' % self.args[0],relative_to=os.getcwd())
        try:
            logging.config.fileConfig(self.args[0])
        except Exception:
            print >> sys.stderr, (
                'Could not configure logging with config file %s' % self.args[0])
        from pyforge import model
        M=model
        log = logging.getLogger('pyforge.command')
        log.info('Initialize reactor with config %r', self.args[0])
        load_environment(conf.global_conf, conf.local_conf)
        pylons.c._push_object(EmptyClass())
        from pyforge.lib.app_globals import Globals
        pylons.g._push_object(Globals())
        ming.configure(**conf)
        self.plugins = [
            (ep.name, ep.load()) for ep in iter_entry_points('pyforge') ]
        log.info('Loaded plugins')

