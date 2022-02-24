#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.


import re
import logging
import os
import time
import six.moves.queue
from contextlib import contextmanager
from datetime import datetime, timedelta
import signal
import sys

import faulthandler
from setproctitle import setproctitle, getproctitle
import tg
from paste.deploy import loadapp
from paste.deploy.converters import asint
from webob import Request

from . import base

faulthandler.enable()

status_log = logging.getLogger('taskdstatus')

log = logging.getLogger(__name__)


@contextmanager
def proctitle(title):
    """Temporarily change the process title, then restore it."""
    orig_title = getproctitle()
    try:
        setproctitle(title)
        yield
        setproctitle(orig_title)
    except Exception:
        setproctitle(orig_title)
        raise


class TaskdCommand(base.Command):
    summary = 'Task server'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('--only', dest='only', type='string', default=None,
                      help='only handle tasks of the given name(s) (can be comma-separated list)')
    parser.add_option('--nocapture', dest='nocapture', action="store_true", default=False,
                      help='Do not capture stdout and redirect it to logging.  Useful for development with pdb.set_trace()')

    def command(self):
        setproctitle('taskd')
        self.basic_setup()
        self.keep_running = True
        self.restart_when_done = False
        base.log.info('Starting taskd, pid %s' % os.getpid())
        signal.signal(signal.SIGHUP, self.graceful_restart)
        signal.signal(signal.SIGTERM, self.graceful_stop)
        signal.signal(signal.SIGUSR1, self.log_current_task)
        # restore default behavior of not interrupting system calls
        # see http://docs.python.org/library/signal.html#signal.siginterrupt
        # and http://linux.die.net/man/3/siginterrupt
        signal.siginterrupt(signal.SIGHUP, False)
        signal.siginterrupt(signal.SIGTERM, False)
        signal.siginterrupt(signal.SIGUSR1, False)
        self.worker()

    def graceful_restart(self, signum, frame):
        base.log.info(
            'taskd pid %s recieved signal %s preparing to do a graceful restart' %
            (os.getpid(), signum))
        self.keep_running = False
        self.restart_when_done = True

    def graceful_stop(self, signum, frame):
        base.log.info(
            'taskd pid %s recieved signal %s preparing to do a graceful stop' %
            (os.getpid(), signum))
        self.keep_running = False

    def log_current_task(self, signum, frame):
        entry = 'taskd pid {} is currently handling task {}'.format(
            os.getpid(), getattr(self, 'task', None))
        status_log.info(entry)
        base.log.info(entry)

    def worker(self):
        from allura import model as M
        name = f'{os.uname()[1]} pid {os.getpid()}'
        wsgi_app = loadapp('config:%s#task' %
                           self.args[0], relative_to=os.getcwd())
        poll_interval = asint(tg.config.get('monq.poll_interval', 10))
        only = self.options.only
        if only:
            only = only.split(',')

        def start_response(status, headers, exc_info=None):
            if status != '200 OK':
                log.warn(
                    'Unexpected http response from taskd request: %s.  Headers: %s',
                    status, headers)

        def waitfunc_noq():
            time.sleep(poll_interval)

        def check_running(func):
            def waitfunc_checks_running():
                if self.keep_running:
                    return func()
                else:
                    raise StopIteration
            return waitfunc_checks_running

        waitfunc = waitfunc_noq
        waitfunc = check_running(waitfunc)
        while self.keep_running:
            try:
                while self.keep_running:
                    self.task = M.MonQTask.get(
                        process=name,
                        waitfunc=waitfunc,
                        only=only)
                    if self.task:
                        with(proctitle("taskd:{}:{}".format(
                                self.task.task_name, self.task._id))):
                            # Build the (fake) request
                            request_path = '/--{}--/{}/'.format(self.task.task_name,
                                                            self.task._id)
                            r = Request.blank(request_path,
                                              base_url=tg.config['base_url'].rstrip(
                                                  '/') + request_path,
                                              environ={'task': self.task,
                                                       'nocapture': self.options.nocapture,
                                                       })
                            list(wsgi_app(r.environ, start_response))
                            self.task = None
            except Exception as e:
                if self.keep_running:
                    base.log.exception(
                        'taskd error %s; pausing for 10s before taking more tasks' % e)
                    time.sleep(10)
                else:
                    base.log.exception('taskd error %s' % e)
        base.log.info('taskd pid %s stopping gracefully.' % os.getpid())

        if self.restart_when_done:
            base.log.info('taskd pid %s restarting itself' % os.getpid())
            os.execv(sys.argv[0], sys.argv)


class TaskCommand(base.Command):
    cmd_default_states = {
        'list': 'ready',
        'count': 'ready',
        'purge': '*'
    }

    summary = 'Task command'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('-s', '--state', dest='state', default=None,
                      help='state of processes for "list", "count", or "purge" subcommands.  * means all. '
                           '(Defaults per command: %s)' %
                           ", ".join([f'{k}="{v}"' for k, v in cmd_default_states.items()]))
    parser.add_option('-t', '--timeout', dest='timeout', type=int, default=60,
                      help='timeout (in seconds) for busy tasks (only applies to "timeout" command)')
    parser.add_option('--filter-name-prefix', dest='filter_name_prefix', default=None,
                      help='limit to task names starting with this.  Example allura.tasks.index_tasks.')
    parser.add_option('--filter-result-regex', dest='filter_result_regex', default=None,
                      help='limit to tasks with result matching this regex.  Example "pysolr"')
    parser.add_option('--filter-queued-days-ago', dest='days_ago', type=int, default=None,
                      help='limit to tasks queued NUM days ago.  Example "180"')
    min_args = 2
    max_args = None
    usage = '''<ini file> [list|count|retry|purge|timeout|commit]

    list: prints tasks matching --state (default: 'ready') and filters
    count: counts tasks matching --state (default: 'ready') and filters
    retry: re-run tasks with 'error' state. --state has no effect
    purge: remove all tasks that match --state ( default: '*') with result_type "forget".
    timeout: retry all tasks with state 'busy' and older than --timeout seconds (does not stop existing task). --state has no effect
    commit: run a solr 'commit' as a background task

    All subcommands except 'commit' can use the --filter-... options.
    '''

    def command(self):
        self.basic_setup()
        cmd = self.args[1]
        tab = dict(
            list=self._list,
            count=self._count,
            retry=self._retry,
            purge=self._purge,
            timeout=self._timeout,
            commit=self._commit)
        tab[cmd]()

    def _get_state_query(self):
        state = self.options.state
        if not state:
            cmd = self.args[1]
            state = self.cmd_default_states.get(cmd, 'ready')

        if state == '*':
            from allura import model as M
            # Providing all possible state values allows us to leverage the mongo index.
            #   omitting a state field might result in an entire COLLSCAN
            state = {'$in': M.MonQTask.states}

        return state

    def _add_filters(self, q):
        if self.options.filter_name_prefix:
            q['task_name'] = {'$regex': fr'^{re.escape(self.options.filter_name_prefix)}.*'}
        if self.options.filter_result_regex:
            q['result'] = {'$regex': self.options.filter_result_regex}
        if self.options.days_ago:
            q['time_queue'] = {'$lt': datetime.utcnow() - timedelta(days=self.options.days_ago)}
        if self.verbose:
            print(q)
        return q

    def _print_query(self, cmd, *args):
        print(f'running mongod cmd: {cmd}, {args}')

    def _list(self):
        '''List tasks'''
        from allura import model as M
        state = self._get_state_query()
        base.log.info('Listing tasks of state %s', state)
        q = dict(state=state)
        q = self._add_filters(q)
        self._print_query('find', q)
        for t in M.MonQTask.query.find(q):
            print(t)

    def _count(self):
        '''Count tasks'''
        from allura import model as M
        state = self._get_state_query()
        base.log.info('Counting tasks of state %s', state)
        q = dict(state=state)
        q = self._add_filters(q)
        self._print_query('find', q)
        count = M.MonQTask.query.find(q).count()
        print('Task Count %s' % count)

    def _retry(self):
        '''Retry tasks in an error state'''
        from allura import model as M
        base.log.info('Retry tasks in error state')
        q = dict(state='error')
        q = self._add_filters(q)
        update = {'$set': dict(state='ready')}
        self._print_query('update', q, update)
        M.MonQTask.query.update(
            q,
            update,
            multi=True)

    def _purge(self):
        '''Purge completed tasks'''
        from allura import model as M
        base.log.info('Purge complete/forget tasks')
        state = self._get_state_query()
        q = dict(state=state, result_type='forget')
        q = self._add_filters(q)
        self._print_query('remove', q)
        M.MonQTask.query.remove(q)

    def _timeout(self):
        '''Reset tasks that have been busy too long to 'ready' state'''
        from allura import model as M
        base.log.info('Reset tasks stuck for %ss or more',
                      self.options.timeout)
        cutoff = datetime.utcnow() - timedelta(seconds=self.options.timeout)
        q = dict(
            state='busy',
            time_start={'$lt': cutoff},
        )
        q = self._add_filters(q)
        update = {'$set': dict(state='ready')}
        self._print_query('update', q, update)
        M.MonQTask.query.update(
            q,
            update,
            multi=True)

    def _commit(self):
        '''Schedule a SOLR commit'''
        from allura.tasks import index_tasks
        base.log.info('Commit to solr')
        index_tasks.commit.post()
