import os
import sys
import time
import logging
from pkg_resources import iter_entry_points
from multiprocessing import Process
from pprint import pformat

import ming
import pylons
from paste.script import command
from paste.deploy import appconfig
from carrot.connection import BrokerConnection
from carrot.messaging import Consumer

from pyforge.config.environment import load_environment
from pyforge import model as M

log=None

class Command(command.Command):
    min_args = max_args = 1
    usage = 'NAME <ini file>'
    group_name = 'PyForge'

    def basic_setup(self):
        global log
        conf = appconfig('config:%s' % self.args[0],relative_to=os.getcwd())
        logging.config.fileConfig(self.args[0])
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

class ReactorSetupCommand(Command):

    summary = 'Configure the RabbitMQ queues and bindings for the given set of plugins'
    parser = command.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        self.backend = pylons.g.conn.create_backend()
        self.reset()
        for name, plugin in self.plugins:
            self.configure_plugin(name, plugin)

    def reset(self):
        'Tear down all queues and bindings'
        be = self.backend
        ch = self.backend.channel
        ch.exchange_delete('audit', nowait=True)
        ch.exchange_delete('react', nowait=True)
        be.exchange_declare('audit', 'topic', True, False)
        be.exchange_declare('react', 'topic', True, False)

    def configure_plugin(self, name, plugin):
        log.info('Configuring plugin %s:%s', name, plugin)
        be = self.backend
        for method, xn, qn, keys in plugin_consumers(name, plugin):
            if be.queue_exists(qn):
                be.channel.queue_delete(qn)
            be.queue_declare(qn, True, False, False, True)
            for k in keys:
                be.queue_bind(exchange=xn, queue=qn, routing_key=k)
            log.info('... %s %s %r', xn, qn, keys)

class ReactorCommand(Command):

    summary = 'Start up all the auditors and reactors for registered plugins'
    parser = command.Command.standard_parser(verbose=True)
    parser.add_option('-p', '--proc', dest='proc', type='int',
                      help='number of worker processes to spawn per queue')

    def command(self):
        self.basic_setup()
        processes = []
        for x in xrange(self.options.proc):
            processes += [
                Process(target=self.worker_main, args=((name,)+ args))
                for name, plugin in self.plugins
                for args in plugin_consumers(name, plugin)]
        for p in processes:
            p.start()
        while True:
            time.sleep(300)
            log.info('=== Mark ===')

    def worker_main(self, plugin_name, method, xn, qn, keys):
        log.info('Entering worker process: %s', qn)
        consumer = Consumer(connection=pylons.g.conn, queue=qn)
        if xn == 'audit':
            consumer.register_callback(self.route_audit(plugin_name, method))
        else:
            consumer.register_callback(self.route_react(plugin_name, method))
        consumer.wait()
        log.info('Exiting worker process: %s', qn)

    def route_audit(self, plugin_name, method):
        'Auditors only respond to their particluar mount point'
        def callback(data, msg):
            msg.ack()
            try:
                pylons.c.project = M.Project.m.get(_id=data['project_id'])
                if method.im_self:
                    method(msg.delivery_info['routing_key'], data)
                else:
                    pylons.c.app = pylons.c.project.app_instance(data['mount_point'])
                    method(pylons.c.app, msg.delivery_info['routing_key'], data)
            except:
                log.exception('Exception audit handling %s: %s', plugin_name, method)
        return callback

    def route_react(self, plugin_name, method):
        'All plugin instances respond to the react exchange'
        def callback(data, msg):
            msg.ack()
            try:
                pylons.c.project = M.Project.m.get(_id=data['project_id'])
                if method.im_self:
                    method(msg.delivery_info['routing_key'], data)
                else:
                    for cfg in pylons.c.project.app_configs:
                        if cfg.plugin_name != plugin_name: continue
                        pylons.c.app = pylons.c.project.app_instance(cfg.options.mount_point)
                        method(pylons.c.app, msg.delivery_info['routing_key'], data)
            except:
                log.exception('Exception react handling %s: %s', plugin_name, method)
        return callback
    
class EmptyClass(object): pass

def plugin_consumers(name, plugin):
    from pyforge.lib.decorators import ConsumerDecoration
    i = 0
    for name in dir(plugin):
        method = getattr(plugin, name)
        deco = ConsumerDecoration.get_decoration(method, False)
        if not deco: continue
        if deco.audit_keys:
            qn = '%s/%d/audit' % (name, i)
            i += 1
            yield method, 'audit', qn, list(deco.audit_keys)
        if deco.react_keys:
            qn = '%s/%d/react' % (name, i)
            i += 1
            yield method, 'react', qn, list(deco.react_keys)

def debug():
    from IPython.ipapi import make_session; make_session()
    from IPython.Debugger import Pdb
    log.info('Entering debugger')
    p = Pdb(color_scheme='Linux')
    p.reset()
    p.setup(sys._getframe(), None)
    p.cmdloop()
    p.forget()
        
    
