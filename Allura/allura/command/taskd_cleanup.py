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

import os
import time
import signal
import socket
import subprocess
from ming.orm.ormsession import ThreadLocalORMSession
import six

from allura import model as M
from . import base


class TaskdCleanupCommand(base.Command):
    summary = 'Tasks cleanup command.  Determines which taskd processes are handling tasks, and what has been dropped or got hung.'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('-k', '--kill-stuck-taskd',
                      dest='kill', action='store_true',
                      help='automatically kill stuck taskd processes.  Be careful with this, a taskd process '
                      'may just be very busy on certain operations and not able to respond to our status request')
    parser.add_option('-n', '--num-retry-status-check',
                      dest='num_retry', type='int', default=5,
                      help='number of retries to read taskd status log after sending USR1 signal (5 by default)')
    usage = '<ini file> [-k] <taskd status log file>'
    min_args = 2
    max_args = 2

    def command(self):
        self.basic_setup()
        self.hostname = socket.gethostname()
        self.taskd_status_log = self.args[1]
        self.stuck_pids = []
        self.error_tasks = []
        self.suspicious_tasks = []

        taskd_pids = self._taskd_pids()
        base.log.info('Taskd processes on %s: %s' %
                      (self.hostname, taskd_pids))

        # find stuck taskd processes
        base.log.info('Seeking for stuck taskd processes')
        for pid in taskd_pids:
            base.log.info('...sending USR1 to %s and watching status log' %
                          (pid))
            status = self._check_taskd_status(int(pid))
            if status != 'OK':
                base.log.info('...taskd pid %s has stuck' % pid)
                self.stuck_pids.append(pid)
                if self.options.kill:
                    base.log.info('...-k is set. Killing %s' % pid)
                    self._kill_stuck_taskd(pid)
            else:
                base.log.info('...%s' % status)

        # find 'forsaken' tasks
        base.log.info('Seeking for forsaken busy tasks')
        tasks = [t for t in self._busy_tasks()
                 if t not in self.error_tasks]  # skip seen tasks
        base.log.info('Found %s busy tasks on %s' %
                      (len(tasks), self.hostname))
        for task in tasks:
            base.log.info('Verifying task %s' % task)
            pid = task.process.split()[-1]
            if pid not in taskd_pids:
                # 'forsaken' task
                base.log.info('Task is forsaken '
                              '(can\'t find taskd with given pid). '
                              'Setting state to \'error\'')
                task.state = 'error'
                task.result = 'Can\'t find taskd with given pid'
                self.error_tasks.append(task)
            else:
                # check if taskd with given pid really processing this task
                # now:
                base.log.info(
                    'Checking that taskd pid %s is really processing task %s' %
                    (pid, task._id))
                status = self._check_task(pid, task)
                if status != 'OK':
                    # maybe task moved quickly and now is complete
                    # so we need to check such tasks later
                    # and mark incomplete ones as 'error'
                    self.suspicious_tasks.append(task)
                    base.log.info('...NO. Adding task to suspisious list')
                else:
                    base.log.info('...OK')

        # check suspicious task and mark incomplete as error
        base.log.info('Checking suspicious list for incomplete tasks')
        self._check_suspicious_tasks()
        ThreadLocalORMSession.flush_all()
        self.print_summary()

    def print_summary(self):
        base.log.info('-' * 80)
        if self.stuck_pids:
            base.log.info('Found stuck taskd: %s' % self.stuck_pids)
            if self.options.kill:
                base.log.info('...stuck taskd processes were killed')
            else:
                base.log.info(
                    '...to kill these processes run command with -k flag if you are sure they are really stuck')
        if self.error_tasks:
            base.log.info('Tasks marked as \'error\': %s' % self.error_tasks)

    def _busy_tasks(self, pid=None):
        regex = '^%s ' % self.hostname
        if pid is not None:
            regex = f'^{self.hostname} pid {pid}'
        return M.MonQTask.query.find({
            'state': 'busy',
            'process': {'$regex': regex}
        })

    def _taskd_pids(self):
        # space or colon after "taskd" to ensure no match on taskd_cleanup (ourself)
        p = subprocess.Popen(['pgrep', '-f', '^taskd[ :]'],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        tasks = []
        if p.returncode == 0:
            tasks = [pid for pid in six.ensure_text(stdout).split('\n') if pid != '']
        return tasks

    def _taskd_status(self, pid, retry=False):
        if not retry:
            os.kill(int(pid), signal.SIGUSR1)
        p = subprocess.Popen(['tail', '-n1', self.taskd_status_log],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        if p.returncode != 0:
            base.log.error('Can\'t read taskd status log %s' %
                           self.taskd_status_log)
            exit(1)
        return six.ensure_text(stdout)

    def _check_taskd_status(self, pid):
        for i in range(self.options.num_retry):
            retry = False if i == 0 else True
            status = self._taskd_status(pid, retry)
            if ('taskd pid %s' % pid) in status:
                return 'OK'
            base.log.info('retrying after one second')
            time.sleep(1)
        return 'STUCK'

    def _check_task(self, taskd_pid, task):
        for i in range(self.options.num_retry):
            retry = False if i == 0 else True
            status = self._taskd_status(taskd_pid, retry)
            line = 'taskd pid {} is currently handling task {}'.format(
                taskd_pid, task)
            if line in status:
                return 'OK'
            base.log.info('retrying after one second')
            time.sleep(1)
        return 'FAIL'

    def _kill_stuck_taskd(self, pid):
        os.kill(int(pid), signal.SIGKILL)
        # find all 'busy' tasks for this pid and mark them as 'error'
        tasks = list(self._busy_tasks(pid=pid))
        base.log.info('...taskd pid %s has assigned tasks: %s. '
                      'setting state to \'error\' for all of them' % (pid, tasks))
        for task in tasks:
            task.state = 'error'
            task.result = 'Taskd has stuck with this task'
            self.error_tasks.append(task)

    def _complete_suspicious_tasks(self):
        complete_tasks = M.MonQTask.query.find({
            'state': 'complete',
            '_id': {'$in': [t._id for t in self.suspicious_tasks]}
        })
        return [t._id for t in complete_tasks]

    def _check_suspicious_tasks(self):
        if not self.suspicious_tasks:
            return
        complete_tasks = self._complete_suspicious_tasks()
        for task in self.suspicious_tasks:
            base.log.info('Verifying task %s' % task)
            if task._id not in complete_tasks:
                base.log.info('...incomplete. Setting status to \'error\'')
                task.state = 'error'
                task.result = 'Forsaken task'
                self.error_tasks.append(task)
            else:
                base.log.info('...complete')
