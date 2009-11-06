from multiprocessing import Process
from time import sleep
import signal
import sys
import os
from datetime import datetime, timedelta

from sf.gutenberg.utils import getLogger, encode_keys
from sf.gutenberg.model import ScheduledTask, GobbleSuccess

class ProcessManager(object):
    """
    Runs N children processes.  If one dies, it starts a new one.
    Should be extended and new_proc() implemented
    If the process receives a SIGTERM, it cleans up its kids
    Only works with one per process, due to how it uses signals
    You must run manager.monitor() after starting it, and that does not return
    """
    one_already_exists = False

    def __init__(self, num_processes, name, target=lambda:None, args=()):
        self.log = getLogger(self.__class__.__module__ + '.' + self.__class__.__name__ + '#' + name)
        if ProcessManager.one_already_exists:
            raise Exception("You can only create one ProcessManager per process")
        else:
            ProcessManager.one_already_exists = True
        self.num_processes = num_processes
        self.name = name
        self.target, self.args = target, args
        self.processes = []
        self.last_death = datetime.fromtimestamp(0)
        self.num_deaths = 0
        self.quitting = False


    def _close_up_shop(self, this_signal, frame):
        self.log.warn("got a %s signal. I am %s" % (this_signal, os.getpid()))
        self.quit()

    def quit(self):
        self.log.warn("quitting")
        # ignore future signals
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        self.quitting = True
        for p in self.processes:
            p.terminate()
        sys.exit()


    def check_children(self):
        if self.quitting:
            return
        for p in self.processes:
            try:
                alive = p.is_alive()
            except OSError, e:
                #self.log.warn('error when checking if %s was alive: %s' % (p.pid, e))
                # p is already long dead
                alive = False
            if not alive:
                if self.last_death + timedelta(minutes=1) > datetime.utcnow():
                    self.num_deaths += 1
                    if self.num_deaths >= self.num_processes:
                        self.log.error("Quitting, since %s child processes died in short succession" % self.num_processes)
                        sys.exit(5)
                else:
                    self.num_deaths = 1
                    self.last_death = datetime.utcnow()
                try:
                    self.log.warn("%s died with exit code %s" % (p.pid, p.exitcode))
                except OSError, e:
                    self.log.error("%s died with unknown exit code" % (p.pid))
                self.processes.remove(p)
                self._start_proc()

    def _child_terminated(self,this_signal,frame):
        self.log.warn("a child died.  I am %s" % os.getpid())
        # can't run process-changing code within a signal handler, the OS doesn't like it
        # and python throws an exception.  See monitor()
        #self.check_children()

    def _start_proc(self):
        p = self.new_proc()
        self.processes.append(p)
        #p.daemon = True
        self.log.debug('starting %s from %s' % (p, os.getpid()))
        p.start()
        self.log.debug('started %s' % p.pid)

    def new_proc(self):
        return Process(target=self.target, args=self.args)

    def start(self):
        for p in range(self.num_processes):
            self._start_proc()
        self.log.debug('all started')
        self.log.info('setting up signals, on pid %s' % os.getpid())
        signal.signal(signal.SIGTERM, self._close_up_shop)
        signal.signal(signal.SIGCHLD, self._child_terminated)

    def monitor(self):
        while True:
            self.check_children()
            # caught signals stop sleep() earlier, which is handy
            # so the sleep(1) ends immediately not waiting for a full second to complete
            sleep(1)


class QueueWorker(object):
    # This class is not thread safe!
    routing_keys=[]
    handle_every_message=False

    def __init__(self, host, queue_name, consumer_factory):
        self.log = getLogger(self)
        self.host = host
        self.queue_name = queue_name
        self.consumer_factory = consumer_factory
        # Note that this is not thread-safe!
        self.current_task=None

    @classmethod
    def test(cls):
        '''Create an instance with faked host/queue_name/consumer_factory'''
        return cls(None, None, None)

    def parse(self, message):
        """ recieves message_data as dict, and must return (shortname, source, details) where details is a dict """
        return message.pop('shortname'), message.pop('source'), message

    def handle(self, shortname, source, **kwargs):
        raise NotImplementedError, '%s.handle' % (self.__class__.__name__)

    def _handle_message(self, message_data, message):
        routing_key = message.delivery_info['routing_key']
        self.log.debug("Message: key=%s, payload=%s", routing_key, message_data)

        if hasattr(message, '_amqp_message'): message.amqp_message = message._amqp_message
        #log.debug("Got delivery info: %s" % message.delivery_info)
        #log.debug("Got properties: %s" % message.amqp_message.properties)
        message_date = message.amqp_message.properties.get('timestamp')

        # Get or create corresponding task
        try:
            if '_task_id' in message_data:
                task_id = message_data.pop('_task_id')
                task = ScheduledTask.start_processing(task_id)
            else:
                task = ScheduledTask.immediate(routing_key, message_data)
            if task is None:
                self.log.warning('task %s not found, so not processing. message was %s' %
                                 (task_id, message_data))
                message.ack()
                return
            (shortname, source, details) = self.parse(message_data)
        except Exception, e:
            self.log.exception('Error parsing message: %s', message_data)
            # FIXME: save message_data somewhere besides log file?
            message.ack()
            return

        # Anti-dogpiling
        if message_date and not self.handle_every_message:
            # if we processed the same type of event successfully, after the time
            # this event changed data,
            # we can skip (e.g. no need to fetch a DOAP again if we just did)
            # generally only happens if there's been a backlog we're catching up on
            already_processed = GobbleSuccess.m.get(
                source = source,
                shortname = shortname,
                queue = self.queue_name,
                date = {'$gt': message_date})
            if already_processed:
                task.retire()
                self.log.debug('skipping %s %s %s %s because we processed a message for it at %s'
                          % (source, shortname, self.queue_name, message_date, already_processed['date']))
                message.ack()
                return

        # Actually handle the message
        try:
            if self.handle(shortname, source, **encode_keys(details)) is not False:
                task.retire()
                GobbleSuccess(dict(
                        date = datetime.utcnow(),
                        queue = self.queue_name,
                        shortname = shortname,
                        source = source,
                        details = details,
                        )).m.insert()
            else:
                self.log.warn('%s returned false; not recording success nor fail',
                         self.__class__.__name__)
        except:
            self.log.warn('%s error', self.__class__.__name__, exc_info=True)
            task.retry()
        message.ack()

    def main(self):
        consumer = self.consumer_factory()
        consumer.register_callback(self._handle_message)
        self.log.debug('Process %s waiting for messages' % os.getpid())
        consumer.wait()
        self.log.warning('wait() ended %s' % os.gitpid())
