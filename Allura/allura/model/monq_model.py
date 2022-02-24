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

import sys
import time
import traceback
import logging
from datetime import datetime, timedelta
import typing

import pymongo
from tg import tmpl_context as c, app_globals as g
from tg import config
from paste.deploy.converters import asbool

import ming
from ming.utils import LazyProperty
from ming import schema as S
from ming.orm import session, FieldProperty
from ming.orm.declarative import MappedClass

from allura.lib.helpers import log_output, null_contextmanager
from .session import task_orm_session

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


log = logging.getLogger(__name__)


class MonQTask(MappedClass):

    '''Task to be executed by the taskd daemon.

    Properties

        - _id - bson.ObjectId() for this task
        - state - 'ready', 'busy', 'error', 'complete', or 'skipped' task status
        - priority - integer priority, higher is more priority
        - result_type - either 'keep' or 'forget', what to do with the task when
          it's done
        - time_queue - time the task was queued
        - time_start - time taskd began working on the task
        - time_stop - time taskd stopped working on the task
        - task_name - full dotted name of the task function to run
        - process - identifier for which taskd process is working on the task
        - context - values used to set c.project, c.app, c.user for the task
        - args - ``*args`` to be sent to the task function
        - kwargs - ``**kwargs`` to be sent to the task function
        - result - if the task is complete, the return value. If in error, the traceback.
    '''
    states = ('ready', 'busy', 'error', 'complete', 'skipped')
    result_types = ('keep', 'forget')

    class __mongometa__:
        session = task_orm_session
        name = 'monq_task'
        indexes = [
            [
                # used in MonQTask.get() method
                # also 'state' queries exist in several other methods
                ('state', ming.ASCENDING),
                ('priority', ming.DESCENDING),
                ('time_queue', ming.ASCENDING)
            ],
            [
                # used by repo tarball status check, etc
                'state', 'task_name', 'time_queue'
            ],
        ]

    query: 'Query[MonQTask]'

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
        user_id=S.ObjectId,
        notifications_disabled=bool))
    args = FieldProperty([])
    kwargs = FieldProperty({None: None})
    result = FieldProperty(None, if_missing=None)

    sort = [
        ('priority', ming.DESCENDING),
        ('time_queue', ming.ASCENDING),
    ]

    def __repr__(self):
        from allura import model as M
        project = M.Project.query.get(_id=self.context.project_id)
        app = None
        if project:
            app_config = M.AppConfig.query.get(_id=self.context.app_config_id)
            if app_config:
                app = project.app_instance(app_config)
        user = M.User.query.get(_id=self.context.user_id)
        project_url = project and project.url() or None
        app_mount = app and app.config.options.mount_point or None
        username = user and user.username or None
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
             priority=10,
             delay=0,
             flush_immediately=True,
             ):
        '''Create a new task object based on the current context.'''
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        task_name = '{}.{}'.format(
            function.__module__,
            function.__name__)
        context = dict(
            project_id=None,
            app_config_id=None,
            user_id=None,
            notifications_disabled=False)
        if getattr(c, 'project', None):
            context['project_id'] = c.project._id
            context[
                'notifications_disabled'] = c.project.notifications_disabled
        if getattr(c, 'app', None):
            context['app_config_id'] = c.app.config._id
        if getattr(c, 'user', None):
            context['user_id'] = c.user._id
        obj = cls(
            state='ready',
            priority=priority,
            result_type=result_type,
            task_name=task_name,
            args=args,
            kwargs=kwargs,
            process=None,
            result=None,
            context=context,
            time_queue=datetime.utcnow() + timedelta(seconds=delay))
        if flush_immediately:
            session(obj).flush(obj)
        return obj

    @classmethod
    def get(cls, process='worker', state='ready', waitfunc=None, only=None):
        '''Get the highest-priority, oldest, ready task and lock it to the
        current process.  If no task is available and waitfunc is supplied, call
        the waitfunc before trying to get the task again.  If waitfunc is None
        and no tasks are available, return None.  If waitfunc raises a
        StopIteration, stop waiting for a task
        '''
        while True:
            try:
                query = dict(state=state)
                query['time_queue'] = {'$lte': datetime.utcnow()}
                if only:
                    query['task_name'] = {'$in': only}
                obj = cls.query.find_and_modify(
                    query=query,
                    update={
                        '$set': dict(
                            state='busy',
                            process=process)
                    },
                    new=True,
                    sort=cls.sort)
                if obj is not None:
                    return obj
            except pymongo.errors.OperationFailure as exc:
                if 'No matching object found' not in exc.args[0]:
                    raise
            if waitfunc is None:
                return None
            try:
                waitfunc()
            except StopIteration:
                return None

    @classmethod
    def run_ready(cls, worker=None):
        '''Run all the tasks that are currently ready'''
        i = 0
        for i, task in enumerate(cls.query.find(dict(state='ready')).sort(cls.sort).all()):
            task.process = worker
            task()
        return i

    def __call__(self, restore_context=True, nocapture=False):
        '''Call the task function with its context.  If restore_context is True,
        c.project/app/user will be restored to the values they had before this
        function was called.
        '''
        from allura import model as M
        self.time_start = datetime.utcnow()
        session(self).flush(self)
        log.info('starting %r', self)
        old_cproject = getattr(c, 'project', None)
        old_capp = getattr(c, 'app', None)
        old_cuser = getattr(c, 'user', None)
        try:
            func = self.function
            c.project = M.Project.query.get(_id=self.context.project_id)
            c.app = None
            if c.project:
                c.project.notifications_disabled = self.context.get(
                    'notifications_disabled', False)
                app_config = M.AppConfig.query.get(
                    _id=self.context.app_config_id)
                if app_config:
                    c.app = c.project.app_instance(app_config)
            c.user = M.User.query.get(_id=self.context.user_id)
            with null_contextmanager() if nocapture else log_output(log):
                self.result = func(*self.args, **self.kwargs)
            self.state = 'complete'
            return self.result
        except Exception as exc:
            if asbool(config.get('monq.raise_errors')):
                raise
            else:
                log.exception('Error "%s" on job %s', exc, self)
                self.state = 'error'
                if hasattr(exc, 'format_error'):
                    self.result = exc.format_error()
                    log.error(self.result)
                else:
                    self.result = traceback.format_exc()
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
