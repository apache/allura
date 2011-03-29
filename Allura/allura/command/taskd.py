import os
import time
import Queue
from datetime import datetime, timedelta

import tg
from paste.deploy import loadapp
from paste.deploy.converters import asint
from webob import Request

import base

class TaskdCommand(base.Command):
    summary = 'Task server'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('-p', '--proc', dest='proc', type='int', default=1,
                      help='number of worker processes to spawn')
    parser.add_option('--dry_run', dest='dry_run', action='store_true', default=False,
                      help="get ready to run the task daemon, but don't actually run it")

    def command(self):
        self.basic_setup()
        processes = [ ]
        for x in xrange(self.options.proc):
            processes.append(base.RestartableProcess(target=self.worker, log=base.log, ))
        if self.options.dry_run: return
        elif self.options.proc == 1:
            base.log.info('Starting single taskd process')
            self.worker()
        else: # pragma no cover
            for p in processes:
                p.start()
            while True:
                for x in xrange(60):
                    time.sleep(5)
                    for p in processes: p.check()
                base.log.info('=== Mark ===')

    def worker(self):
        from allura import model as M
        name = '%s pid %s' % (os.uname()[1], os.getpid())
        if self.options.dry_run: return
        wsgi_app = loadapp('config:%s#task' % self.args[0],relative_to=os.getcwd())
        def start_response(status, headers, exc_info=None):
            pass
        def waitfunc_amqp():
            poll_interval = asint(self.config.get('monq.poll_interval', 10))
            try:
                return tg.g.amq_conn.queue.get(timeout=poll_interval)
            except Queue.Empty:
                return None
        def waitfunc_noq():
            poll_interval = asint(self.config.get('monq.poll_interval', 10))
            time.sleep(poll_interval)
        if self.globals.amq_conn:
            waitfunc = waitfunc_amqp
        else:
            waitfunc = waitfunc_noq
        while True:
            if self.globals.amq_conn:
                tg.g.amq_conn.reset()
            try:
                while True:
                    task = M.MonQTask.get(process=name, waitfunc=waitfunc)
                    # Build the (fake) request
                    r = Request.blank('/--%s--/' % task.task_name, dict(task=task))
                    list(wsgi_app(r.environ, start_response))
            except Exception:
                base.log.exception('Taskd, restart in 10s')
                time.sleep(10)


class TaskCommand(base.Command):
    summary = 'Task command'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('-s', '--state', dest='state', default='ready',
                      help='state of processes to examine')
    parser.add_option('-t', '--timeout', dest='timeout', type=int, default=60,
                      help='timeout (in seconds) for busy tasks')
    min_args = 2
    max_args = None
    usage = '<ini file> [list|retry|purge|timeout|commit]'

    def command(self):
        self.basic_setup()
        cmd = self.args[1]
        tab = dict(
            list=self._list,
            retry=self._retry,
            purge=self._purge,
            timeout=self._timeout,
            commit=self._commit)
        tab[cmd]()

    def _list(self):
        '''List tasks'''
        from allura import model as M
        base.log.info('Listing tasks of state %s', self.options.state)
        if self.options.state == '*':
            q = dict()
        else:
            q = dict(state=self.options.state)
        for t in M.MonQTask.query.find(q):
            print t

    def _retry(self):
        '''Retry tasks in an error state'''
        from allura import model as M
        base.log.info('Retry tasks in error state')
        M.MonQTask.query.update(
            dict(state='error'),
            {'$set': dict(state='ready')},
            multi=True)

    def _purge(self):
        '''Purge completed tasks'''
        from allura import model as M
        base.log.info('Purge complete/forget tasks')
        M.MonQTask.query.remove(
            dict(state='complete', result_type='forget'))

    def _timeout(self):
        '''Reset tasks that have been busy too long to 'ready' state'''
        from allura import model as M
        base.log.info('Reset tasks stuck for %ss or more', self.options.timeout)
        cutoff = datetime.utcnow() - timedelta(seconds=self.options.timeout)
        M.MonQTask.timeout_tasks(cutoff)

    def _commit(self):
        '''Schedule a SOLR commit'''
        from allura.tasks import index_tasks
        base.log.info('Commit to solr')
        index_tasks.commit.post()
