import os
import sys
import logging
from pkg_resources import iter_entry_points

import pylons
from paste.script import command
from paste.deploy import appconfig

import ming
from pyforge.config.environment import load_environment
from pyforge.lib.custom_middleware import MagicalC, environ

class EmptyClass(object): pass

class Command(command.Command):
    min_args = 0
    max_args = 1
    usage = 'NAME [<ini file>]'
    group_name = 'PyForge'

    def basic_setup(self):
        global log, M
        if self.args:
            conf = appconfig('config:%s' % self.args[0],relative_to=os.getcwd())
            try:
                if self.setup_global_config:
                    logging.config.fileConfig(self.args[0])
            except Exception:
                try:
                    # logging does not understand section#subsection syntax,
                    # so strip away the #subsection and try again.
                    logging.config.fileConfig(self.args[0].split('#')[0])
                except Exception:
                    print >> sys.stderr, (
                        'Could not configure logging with config file %s' % self.args[0])
            from pyforge import model
            M=model
            log = logging.getLogger('pyforge.command')
            log.info('Initialize reactor with config %r', self.args[0])
            environ.set_environment({})
            load_environment(conf.global_conf, conf.local_conf)
            try:
                pylons.c._current_obj()
            except TypeError:
                pylons.c._push_object(MagicalC(EmptyClass(), environ))
            from pyforge.lib.app_globals import Globals
            pylons.g._push_object(Globals())
            ming.configure(**conf)
        else:
            log = logging.getLogger('pyforge.command')
        self.tools = [
            (ep.name, ep.load()) for ep in iter_entry_points('pyforge') ]
        log.info('Loaded tools')

