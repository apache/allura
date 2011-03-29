import sys
import time
import traceback
import logging
from datetime import datetime

import pymongo
from tg import c, g

import ming
from ming.utils import LazyProperty
from ming import schema as S
from ming.orm import session, MappedClass, FieldProperty

from .session import main_orm_session

log = logging.getLogger(__name__)

class MonQTask(MappedClass):
    '''Task to be executed by the taskd daemon.

    Properties

        - _id - bson.ObjectId() for this task
        - state - 'ready', 'busy', 'error', or 'complete' task status
        - priority - integer priority, higher is more priority
        - result_type - either 'keep' or 'forget', what to do with the task when
          it's done
        - time_queue - time the task was queued
        - time_start - time taskd began working on the task
        - time_stop - time taskd stopped working on the task
        - task_name - full dotted name of the task function to run
        - process - identifier for which taskd process is working on the task
        - context - values used to set c.project, c.app, c.user for the task
        - args - *args to be sent to the task function
        - kwargs - **kwargs to be sent to the task function
        - result - if the task is complete, the return value. If in error, the traceback.
    '''
    states = ('ready', 'busy', 'error', 'complete')
    result_types = ('keep', 'forget')
    class __mongometa__:
        session = main_orm_session
        name = 'monq_task'
        indexes = [
           [ ('state', ming.ASCENDING),
             ('priority', ming.DESCENDING),
             ('time_queue', ming.ASCENDING) ],
           ['state', 'time_queue'],
           ]

    _id = FieldProperty(S.ObjectId)
    state = FieldProperty(S.OneOf(*states))
    priority = FieldProperty(int)
    result_type = FieldProperty(S.OneOf(*result_types))
    time_queue = FieldProperty(datetime, if_missing=datetime.utcnow)
    time_start = FieldProperty(datetime, if_missing=None)
    time_stop = FieldProperty(datetime, if_missing=None)

    task_name = FieldProperty(str)
    process = FieldProperty(str)
    context = FieldProperty(dict(
            project_id=S.ObjectId,
            app_config_id=S.ObjectId,
            user_id=S.ObjectId))
    args = FieldProperty([])
    kwargs = FieldProperty({None:None})
    result = FieldProperty(None, if_missing=None)

    def __repr__(self):
        from allura import model as M
        c.project = M.Project.query.get(_id=self.context.project_id)
        c.app = None
        if c.project:
            app_config = M.AppConfig.query.get(_id=self.context.app_config_id)
            if app_config:
                c.app = c.project.app_instance(app_config)
        c.user = M.User.query.get(_id=self.context.user_id)
        project_url = c.project and c.project.url() or None
        app_mount = c.app and c.app.config.options.mount_point or None
        username = c.user and c.user.username or None
        return '<%s %s (%s) P:%d %s %s project:%s app:%s user:%s>' % (
            self.__class__.__name__,
            self._id,
            self.state,
            self.priority,
            self.task_name,
            self.process,
            project_url,
            app_mount,
            username)

    @LazyProperty
    def function(self):
        '''The function that is called by this task'''
        smod, sfunc = self.task_name.rsplit('.', 1)
        cur = __import__(smod, fromlist=[sfunc])
        return getattr(cur, sfunc)

    @classmethod
    def post(cls,
             function,
             args=None,
             kwargs=None,
             result_type='forget',
             priority=10):
        '''Create a new task object based on the current context.'''
        if args is None: args = ()
        if kwargs is None: kwargs = {}
        task_name = '%s.%s' % (
            function.__module__,
            function.__name__)
        context = dict(
            project_id=None,
            app_config_id=None,
            user_id=None)
        if getattr(c, 'project', None):
            context['project_id']=c.project._id
        if getattr(c, 'app', None):
            context['app_config_id']=c.app.config._id
        if getattr(c, 'user', None):
            context['user_id']=c.user._id
        obj = cls(
            state='ready',
            priority=priority,
            result_type=result_type,
            task_name=task_name,
            args=args,
            kwargs=kwargs,
            process=None,
            result=None,
            context=context)
        session(obj).flush(obj)
        try:
            if g.amq_conn:
                g.amq_conn.queue.put('')
        except:
            log.warning('Error putting to amq_conn', exc_info=True)
        return obj

    @classmethod
    def get(cls, process='worker', state='ready', waitfunc=None):
        '''Get the highest-priority, oldest, ready task and lock it to the
        current process.  If no task is available and waitfunc is supplied, call
        the waitfunc before trying to get the task again.  If waitfunc is None
        and no tasks are available, return None.
        '''
        sort = [
                ('priority', ming.DESCENDING),
                ('time_queue', ming.ASCENDING)]
        while True:
            try:
                obj = cls.query.find_and_modify(
                    query=dict(state=state),
                    update={
                        '$set': dict(
                            state='busy',
                            process=process)
                        },
                    new=True,
                    sort=sort)
                if obj is not None: return obj
            except pymongo.errors.OperationFailure, exc:
                if 'No matching object found' not in exc.args[0]:
                    raise
            if waitfunc is None:
                return None
            waitfunc()

    @classmethod
    def timeout_tasks(cls, older_than):
        '''Mark all busy tasks older than a certain datetime as 'ready' again.
        Used to retry 'stuck' tasks.'''
        spec = dict(state='busy')
        spec['time_start'] = {'$lt':older_than}
        cls.query.update(spec, {'$set': dict(state='ready')}, multi=True)

    @classmethod
    def clear_complete(cls):
        '''Delete the task objects for complete tasks'''
        spec = dict(state='complete')
        cls.query.remove(spec)

    @classmethod
    def run_ready(cls, worker=None):
        '''Run all the tasks that are currently ready'''
        i=0
        for i, task in enumerate(cls.query.find(dict(state='ready')).all()):
            task.process = worker
            task()
        return i

    def __call__(self, restore_context=True):
        '''Call the task function with its context.  If restore_context is True,
        c.project/app/user will be restored to the values they had before this
        function was called.
        '''
        from allura import model as M
        self.time_start = datetime.utcnow()
        session(self).flush(self)
        log.info('%r', self)
        old_cproject = getattr(c, 'project', None)
        old_capp = getattr(c, 'app', None)
        old_cuser = getattr(c, 'user', None)
        try:
            func = self.function
            c.project = M.Project.query.get(_id=self.context.project_id)
            c.app = None
            if c.project:
                app_config = M.AppConfig.query.get(_id=self.context.app_config_id)
                if app_config:
                    c.app = c.project.app_instance(app_config)
            c.user = M.User.query.get(_id=self.context.user_id)
            self.result = func(*self.args, **self.kwargs)
            self.state = 'complete'
            return self.result
        except Exception, exc:
            log.exception('%r', self)
            self.state = 'error'
            if hasattr(exc, 'format_error'):
                self.result = exc.format_error()
                log.error(self.result)
            else:
                self.result = traceback.format_exc()
            raise
        finally:
            self.time_stop = datetime.utcnow()
            session(self).flush(self)
            if restore_context:
                c.project = old_cproject
                c.app = old_capp
                c.user = old_cuser

    def join(self, poll_interval=0.1):
        '''Wait until this task is either complete or errors out, then return the result.'''
        while self.state not in ('complete', 'error'):
            time.sleep(poll_interval)
            self.query.find(dict(_id=self._id), refresh=True).first()
        return self.result

    @classmethod
    def list(cls, state='ready'):
        '''Print all tasks of a certain status to sys.stdout.  Used for debugging.'''
        for t in cls.query.find(dict(state=state)):
            sys.stdout.write('%r\n' % t)
