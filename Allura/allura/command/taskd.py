import os
import time
import Queue
from datetime import datetime, timedelta

import faulthandler
import pylons
from paste.deploy import loadapp
from paste.deploy.converters import asint
from webob import Request

import base

faulthandler.enable()


class TaskdCommand(base.Command):
    summary = 'Task server'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('--only', dest='only', type='string', default=None,
                      help='only handle tasks of the given name(s) (can be comma-separated list)')
    parser.add_option('--exclude', dest='exclude', type='string', default=None,
                      help='never handle tasks of the given name(s) (can be comma-separated list)')

    def command(self):
        self.basic_setup()
        base.log.info('Starting single taskd process')
        self.worker()

    def worker(self):
        from allura import model as M
        name = '%s pid %s' % (os.uname()[1], os.getpid())
        wsgi_app = loadapp('config:%s#task' % self.args[0],relative_to=os.getcwd())
        poll_interval = asint(pylons.config.get('monq.poll_interval', 10))
        only = self.options.only
        if only:
            only = only.split(',')
        exclude = self.options.exclude
        if exclude:
            exclude = exclude.split(',')
        def start_response(status, headers, exc_info=None):
            pass
        def waitfunc_amqp():
            try:
                return pylons.g.amq_conn.queue.get(timeout=poll_interval)
            except Queue.Empty:
                return None
        def waitfunc_noq():
            time.sleep(poll_interval)
        if pylons.g.amq_conn:
            waitfunc = waitfunc_amqp
        else:
            waitfunc = waitfunc_noq
        while True:
            if pylons.g.amq_conn:
                pylons.g.amq_conn.reset()
            try:
                while True:
                    task = M.MonQTask.get(
                            process=name,
                            waitfunc=waitfunc,
                            only=only,
                            exclude=exclude)
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
