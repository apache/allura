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
        try:
            ch.exchange_delete('audit')
        except:
            log.warning('Error deleting audit exchange')
            self.backend = be = pylons.g.conn.create_backend()
            ch = self.backend.channel
        try:
            ch.exchange_delete('react')
        except:
            log.warning('Error deleting react exchange')
            self.backend = be = pylons.g.conn.create_backend()
            ch = self.backend.channel
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
    parser.add_option('-p', '--proc', dest='proc', type='int', default=1,
                      help='number of worker processes to spawn')

    def command(self):
        self.basic_setup()
        processes = [ Process(target=self.periodic_main, args=()) ]
        configs = [
            dict(plugin_name=name,
                 method=method, xn=xn, qn=qn, keys=keys)
            for name, plugin in self.plugins
            for method, xn, qn, keys in plugin_consumers(name, plugin) ]
        for x in xrange(self.options.proc):
            processes.append(Process(target=self.multi_worker_main,
                                     args=(configs,)))
            continue
            processes += [
                Process(target=self.worker_main, args=((name,)+ args))
                for name, plugin in self.plugins
                for args in plugin_consumers(name, plugin)]
        for p in processes:
            p.start()
        while True:
            time.sleep(300)
            log.info('=== Mark ===')

    def multi_worker_main(self, configs):
        log.info('Entering multiqueue worker process')
        consumers = [ ]
        cset = ConsumerSet(pylons.g.conn)
        for config in configs:
            c = Consumer(connection=pylons.g.conn, queue=config['qn'])
            if config['xn'] == 'audit':
                c.register_callback(self.route_audit(config['plugin_name'], config['method']))
            else:
                c.register_callback(self.route_react(config['plugin_name'], config['method']))
            cset.add_consumer(c)
        for x in cset.iterconsume():
            pass

    def worker_main(self, plugin_name, method, xn, qn, keys):
        log.info('Entering worker process: %s', qn)
        consumer = Consumer(connection=pylons.g.conn, queue=qn)
        if xn == 'audit':
            consumer.register_callback(self.route_audit(plugin_name, method))
        else:
            consumer.register_callback(self.route_react(plugin_name, method))
        consumer.wait()
        log.info('Exiting worker process: %s', qn)

    def periodic_main(self):
        log.info('Entering periodic reactor')
        while True:
            M.ScheduledMessage.fire_when_ready()
            time.sleep(5)

    def route_audit(self, plugin_name, method):
        'Auditors only respond to their particluar mount point'
        def callback(data, msg):
            msg.ack()
            try:
                log.info('***Message received:%s', data)
                project_id = data.get('project_id')
                if project_id:
                    pylons.c.project = M.Project.query.get(_id=project_id)
                else:
                    pylons.c.project = None
                if pylons.c.project is None and project_id:
                    log.error('The project_id was %s but it was not found',
                              project_id)
                mount_point = data.get('mount_point')
                if mount_point is not None:
                    pylons.c.app = pylons.c.project.app_instance(mount_point)
                    log.debug('Setting app %s', pylons.c.app)
                if getattr(method, 'im_self', ()) is None:
                    log.debug('im_self is None')
                    # Instancemethod - call, binding self
                    method(pylons.c.app, msg.delivery_info['routing_key'], data)
                else:
                    # Classmethod or function - don't bind self
                    method(msg.delivery_info['routing_key'], data)
            except:
                log.exception('Exception audit handling %s: %s',
                              plugin_name, method)
            else:
                ming.orm.ormsession.ThreadLocalORMSession.flush_all()
            finally:
                ming.orm.ormsession.ThreadLocalORMSession.close_all()
                
        return callback

    def route_react(self, plugin_name, method):
        'All plugin instances respond to the react exchange'
        def callback(data, msg):
            msg.ack()
            try:
                # log.info('React(%s): %s', msg.delivery_info['routing_key'], data)
                pylons.c.project = M.Project.query.get(_id=data['project_id'])
                mount_point = data.get('mount_point')
                if getattr(method, 'im_self', ()) is None:
                    # Instancemethod - call once for each app, binding self
                    for cfg in pylons.c.project.app_configs:
                        if cfg.plugin_name != plugin_name: continue
                        pylons.c.app = pylons.c.project.app_instance(
                            cfg.options.mount_point)
                        method(pylons.c.app, msg.delivery_info['routing_key'], data)
                else:
                    # Classmethod or function -- just call once 
                    method(msg.delivery_info['routing_key'], data)
            except:
                log.exception('Exception react handling %s: %s', plugin_name, method)
            else:
                ming.orm.ormsession.ThreadLocalORMSession.flush_all()
            finally:
                ming.orm.ormsession.ThreadLocalORMSession.close_all()
        return callback

class SendMessageCommand(Command):
    min_args=3
    max_args=4
    usage = 'NAME <ini file> <exchange> <topic> [<json message>]'
    summary = 'Send a message to a RabbitMQ exchange'
    parser = command.Command.standard_parser(verbose=True)
    parser.add_option('-c', '--context', dest='context',
                      help=('The context of the message (path to the project'
                            ' and/or plugin'))

    def command(self):
        from pyforge.lib.helpers import find_project
        self.basic_setup()
        exchange = self.args[1]
        topic = self.args[2]
        # Set the context of the message
        if self.options.context:
            project, rest = find_project(self.options.context.split('/'))
            pylons.c.project = project
            if rest:
                pylons.g.set_app(rest[0])
        if len(self.args) > 3:
            base_message = json.loads(self.args[3])
        else:
            base_message = json.loads(sys.stdin.read())
        log.info('Sending message to %s / %s:\n%s',
                 exchange, topic, base_message)
        pylons.g.publish(exchange, topic, base_message)

class EmptyClass(object): pass

def plugin_consumers(name, plugin):
    from pyforge.lib.decorators import ConsumerDecoration
    i = 0
    for name in dir(plugin):
        method = getattr(plugin, name)
        deco = ConsumerDecoration.get_decoration(method, False)
        if not deco: continue
        name = '%s.%s' % (method.__module__, method.__name__)
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
        
    
