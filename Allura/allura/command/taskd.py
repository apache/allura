import os
import time
import Queue

import pylons
import ming.orm
from paste.deploy import loadapp
from webob import Request

import base

class TaskdCommand(base.Command):
    summary = 'Task server'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('-p', '--proc', dest='proc', type='int', default=1,
                      help='number of worker processes to spawn')
    parser.add_option('--dry_run', dest='dry_run', action='store_true', default=False,
                      help="get ready to run the reactor, but don't actually run it")

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
        wsgi_app = loadapp('config:%s' % self.args[0],relative_to=os.getcwd())
        def start_response(status, headers, exc_info=None):
            pass
        while True:
            pylons.g.amq_conn.reset()
            def waitfunc():
                try:
                    return pylons.g.amq_conn.queue.get(timeout=10)
                except Queue.Empty:
                    return None
            try:
                while True:
                    task = M.MonQTask.get(process=name, waitfunc=waitfunc)
                    base.log.info('Got task %r', task)
                    # Build the (fake) request
                    r = Request.blank('/--%s--/' % task.task_name, dict(task=task))
                    list(wsgi_app(r.environ, start_response))
                    ming.orm.ormsession.ThreadLocalORMSession.flush_all()
                    ming.orm.ormsession.ThreadLocalORMSession.close_all()
            except Exception:
                base.log.exception('Taskd, restart in 10s')
                time.sleep(10)
