import os
import sys
import logging
from pkg_resources import iter_entry_points

import pylons
from paste.script import command
from paste.deploy import appconfig

import ming
from allura.config.environment import load_environment
from allura.lib.custom_middleware import MagicalC, environ
from allura.lib import security

class EmptyClass(object): pass

class Command(command.Command):
    min_args = 0
    max_args = 1
    usage = 'NAME [<ini file>]'
    group_name = 'Allura'

    def basic_setup(self):
        global log, M
        if self.args:
            conf = appconfig('config:%s' % self.args[0],relative_to=os.getcwd())
            try:
                if self.setup_global_config:
                    logging.config.fileConfig(self.args[0], disable_existing_loggers=False)
            except Exception:
                try:
                    # logging does not understand section#subsection syntax,
                    # so strip away the #subsection and try again.
                    logging.config.fileConfig(self.args[0].split('#')[0], disable_existing_loggers=False)
                except Exception: # pragma no cover
                    print >> sys.stderr, (
                        'Could not configure logging with config file %s' % self.args[0])
            from allura import model
            M=model
            log = logging.getLogger('allura.command')
            log.info('Initialize reactor with config %r', self.args[0])
            environ.set_environment({
                    'allura.credentials':security.Credentials()
                    })
            load_environment(conf.global_conf, conf.local_conf)
            try:
                pylons.c._current_obj()
            except TypeError:
                pylons.c._push_object(MagicalC(EmptyClass(), environ))
            from allura.lib.app_globals import Globals
            pylons.g._push_object(Globals())
            ming.configure(**conf)
        else:
            log = logging.getLogger('allura.command')
        self.tools = []
        for ep in iter_entry_points('allura'):
            try:
                self.tools.append((ep.name, ep.load()))
            except ImportError:
                log.warning('Canot load entry point %s', ep)
        for ep in iter_entry_points('allura.command_init'):
            log.info('Running reactor_init for %s', ep.name)
            ep.load()(conf)
        log.info('Loaded tools')

