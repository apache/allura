import sys
import time
import json
from multiprocessing import Process

import ming
import pylons
from pymongo.bson import ObjectId
from carrot.messaging import Consumer, ConsumerSet

from . import base

class RestartableProcess(object):

    def __init__(self, log, *args, **kwargs):
        self._log = log
        self._args, self._kwargs = args, kwargs
        self.reinit()

    def reinit(self):
        self._process = Process(*self._args, **self._kwargs)

    def check(self):
        if not self.is_alive():
            self._log.error('Process %d has died, restarting', self.pid)
            self.reinit()
            self.start()

    def __getattr__(self, name):
        return getattr(self._process, name)

class ReactorSetupCommand(base.Command):

    summary = 'Configure the RabbitMQ queues and bindings for the given set of tools'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        self.backend = pylons.g.conn.create_backend()
        self.reset()
        for name, tool in self.tools:
            self.configure_tool(name, tool)

    def reset(self):
        'Tear down all queues and bindings'
        be = self.backend
        ch = self.backend.channel
        try:
            ch.exchange_delete('audit')
        except: # pragma no cover
            base.log.warning('Error deleting audit exchange')
            self.backend = be = pylons.g.conn.create_backend()
            ch = self.backend.channel
        try:
            ch.exchange_delete('react')
        except: # pragma no cover
            base.log.warning('Error deleting react exchange')
            self.backend = be = pylons.g.conn.create_backend()
            ch = self.backend.channel
        be.exchange_declare('audit', 'topic', True, False)
        be.exchange_declare('react', 'topic', True, False)

    def configure_tool(self, name, tool):
        base.log.info('Configuring tool %s:%s', name, tool)
        be = self.backend
        for method, xn, qn, keys in tool_consumers(name, tool):
            if be.queue_exists(qn):
                be.channel.queue_delete(qn)
            be.queue_declare(qn, True, False, False, True)
            for k in keys:
                be.queue_bind(exchange=xn, queue=qn, routing_key=k)
            base.log.info('... %s %s %r', xn, qn, keys)

class ReactorCommand(base.Command):

    summary = 'Start up all the auditors and reactors for registered tools'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('-p', '--proc', dest='proc', type='int', default=1,
                      help='number of worker processes to spawn')
    parser.add_option('--dry_run', dest='dry_run', action='store_true', default=False,
                      help="get ready to run the reactor, but don't actually run it")

    def command(self):
        self.basic_setup()
        processes = [ RestartableProcess(target=self.periodic_main, log=base.log, args=()) ]
        configs = [
            dict(tool_name=name,
                 method=method, xn=xn, qn=qn, keys=keys)
            for name, tool in self.tools
            for method, xn, qn, keys in tool_consumers(name, tool) ]
        for x in xrange(self.options.proc):
            processes.append(RestartableProcess(target=self.multi_worker_main,
                                     log=base.log,
                                     args=(configs,)))
            continue
        if self.options.dry_run: return configs
        elif self.options.proc == 1:
            base.log.info('Starting single reactor process')
            processes[0].start()
            self.multi_worker_main(configs)
        else: # pragma no cover
            for p in processes:
                p.start()
            while True:
                for x in xrange(60):
                    time.sleep(5)
                    for p in processes: p.check()
                base.log.info('=== Mark ===')

    def multi_worker_main(self, configs):
        base.log.info('Entering multiqueue worker process')
        consumers = [ ]
        cset = ConsumerSet(pylons.g.conn)
        for config in configs:
            c = Consumer(connection=pylons.g.conn, queue=config['qn'])
            if config['xn'] == 'audit':
                c.register_callback(self.route_audit(config['tool_name'], config['method']))
            else:
                c.register_callback(self.route_react(config['tool_name'], config['method']))
            cset.add_consumer(c)
        if self.options.dry_run: return
        else: # pragma no cover
            base.log.info('Ready to handle messages')
            for x in cset.iterconsume():
                pass

    def periodic_main(self):
        base.log.info('Entering periodic reactor')
        while True:
            base.M.ScheduledMessage.fire_when_ready()
            time.sleep(5)
            if self.options.dry_run: return

    def route_audit(self, tool_name, method):
        'Auditors only respond to their particluar mount point'
        def callback(data, msg):
            msg.ack()
            try:
                if 'project_id' in data:
                    try:
                        if data['project_id']:
                            pylons.c.project = base.M.Project.query.get(_id=ObjectId(str(data['project_id'])))
                        else:
                            pylons.c.project = None
                    except:
                        pylons.c.project = None
                        base.log.exception('Error looking up project %r', data['project_id'])
                    if pylons.c.project is None:
                        base.log.error('The project_id was %s but it was not found',
                                       data['project_id'])
                else:
                    pylons.c.project = None
                if 'user_id' in data:
                    try:
                        pylons.c.user = base.M.User.query.get(
                            _id=data['user_id'] and ObjectId(str(data['user_id'])) or None)
                    except:
                        base.log.exception('Bad user_id: %s', data['user_id'])
                mount_point = data.get('mount_point')
                if pylons.c.project and mount_point is not None:
                    pylons.c.app = pylons.c.project.app_instance(mount_point)
                    base.log.debug('Setting app %s', pylons.c.app)
                if getattr(method, 'im_self', ()) is None:
                    # Instancemethod - call, binding self
                    method(pylons.c.app, msg.delivery_info['routing_key'], data)
                else:
                    # Classmethod or function - don't bind self
                    method(msg.delivery_info['routing_key'], data)
            except: # pragma no cover
                base.log.exception('Exception audit handling %s: %s',
                                   tool_name, method)
                if self.options.dry_run: raise
            else:
                ming.orm.ormsession.ThreadLocalORMSession.flush_all()
            finally:
                ming.orm.ormsession.ThreadLocalORMSession.close_all()
                
        return callback

    def route_react(self, tool_name, method):
        'All tool instances respond to the react exchange'
        def callback(data, msg):
            msg.ack()
            try:
                # log.info('React(%s): %s', msg.delivery_info['routing_key'], data)
                if 'user_id' in data:
                    try:
                        pylons.c.user = base.M.User.query.get(_id=data['user_id'] and ObjectId(str(data['user_id'])) or None)
                    except:
                        base.log.exception('Bad user_id: %s', data['user_id'])
                if 'project_id' in data:
                    try:
                        if data['project_id']:
                            pylons.c.project = base.M.Project.query.get(_id=ObjectId(str(data['project_id'])))
                        else:
                            pylons.c.project = None
                    except:
                        pylons.c.project = None
                        base.log.exception('Error looking up project %r', data['project_id'])
                if getattr(method, 'im_self', ()) is None:
                    # Instancemethod - call once for each app, binding self
                    if not pylons.c.project:
                        # Can't route it, so drop
                        return
                    for cfg in pylons.c.project.app_configs:
                        if cfg.tool_name != tool_name: continue
                        pylons.c.app = pylons.c.project.app_instance(
                            cfg.options.mount_point)
                        method(pylons.c.app, msg.delivery_info['routing_key'], data)
                else:
                    # Classmethod or function -- just call once 
                    method(msg.delivery_info['routing_key'], data)
            except: # pragma no cover
                base.log.exception('Exception react handling %s: %s', tool_name, method)
                if self.options.dry_run: raise
            else:
                ming.orm.ormsession.ThreadLocalORMSession.flush_all()
            finally:
                ming.orm.ormsession.ThreadLocalORMSession.close_all()
        return callback

class SendMessageCommand(base.Command):
    min_args=3
    max_args=4
    usage = 'NAME <ini file> <exchange> <topic> [<json message>]'
    summary = 'Send a message to a RabbitMQ exchange'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('-c', '--context', dest='context',
                      help=('The context of the message (path to the project'
                            ' and/or tool'))

    def command(self):
        from pyforge.lib.helpers import find_project
        self.basic_setup()
        exchange = self.args[1]
        topic = self.args[2]
        # Set the context of the message
        if self.options.context:
            project, rest = find_project(self.options.context)
            pylons.c.project = project
            if rest:
                pylons.g.set_app(rest[0])
        if len(self.args) > 3:
            base_message = json.loads(self.args[3])
        else:  # pragma no cover
            base_message = json.loads(sys.stdin.read())
        base.log.info('Sending message to %s / %s:\n%s',
                      exchange, topic, base_message)
        pylons.g.publish(exchange, topic, base_message)

def tool_consumers(name, tool):
    from pyforge.lib.decorators import ConsumerDecoration
    i = 0
    for name in dir(tool):
        method = getattr(tool, name)
        deco = ConsumerDecoration.get_decoration(method, False)
        if not deco: continue
        if not hasattr(method, '__name__'): continue
        name = '%s.%s' % (method.__module__, method.__name__)
        if deco.audit_keys:
            qn = '%s/%d/audit' % (name, i)
            i += 1
            yield method, 'audit', qn, list(deco.audit_keys)
        if deco.react_keys:
            qn = '%s/%d/react' % (name, i)
            i += 1
            yield method, 'react', qn, list(deco.react_keys)

def debug(): # pragma no cover
    from IPython.ipapi import make_session; make_session()
    from IPython.Debugger import Pdb
    base.log.info('Entering debugger')
    p = Pdb(color_scheme='Linux')
    p.reset()
    p.setup(sys._getframe(), None)
    p.cmdloop()
    p.forget()
