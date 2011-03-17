import time
import traceback
import logging
from cPickle import dumps, loads
from datetime import datetime

import bson
import pymongo
from pylons import c

import ming
from ming import schema as S
from ming.orm import session, MappedClass, FieldProperty

from allura.lib import helpers as h

from .session import main_orm_session

log = logging.getLogger(__name__)

class MonQTask(MappedClass):
    states = ('ready', 'busy', 'error', 'complete')
    result_types = ('keep', 'forget')
    class __mongometa__:
        session = main_orm_session
        name = 'monq_task'
        indexes = [
           [ ('state', ming.ASCENDING),
             ('priority', ming.DESCENDING),
             ('timestamp', ming.ASCENDING) ],
           ['state', 'timestamp'],
           ]

    _id = FieldProperty(S.ObjectId)
    state = FieldProperty(S.OneOf(*states))
    priority = FieldProperty(int)
    result_type = FieldProperty(S.OneOf(*result_types))
    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)

    task_name = FieldProperty(str)
    function = FieldProperty(S.Binary)
    process = FieldProperty(str)
    context = FieldProperty(dict(
            project_id=S.ObjectId,
            app_config_id=S.ObjectId,
            user_id=S.ObjectId))
    args = FieldProperty([])
    kwargs = FieldProperty({})
    result = FieldProperty(None, if_missing=None)

    def __repr__(self):
        return '<%s %s (%s) P:%d %s %s>' % (
            self.__class__.__name__,
            self._id,
            self.state,
            self.priority,
            self.task_name,
            self.process)

    @classmethod
    def post(cls,
             function,
             args=None,
             kwargs=None,
             task_name=None,
             result_type='forget',
             priority=10):
        if task_name is None:
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
            function=bson.Binary(dumps(function)),
            args=args,
            kwargs=kwargs,
            process=None,
            result=None,
            context=context)
        return obj

    @classmethod
    def get(cls, process='worker', state='ready', waitfunc=None):
        sort = [
                ('priority', ming.DESCENDING),
                ('timestamp', ming.ASCENDING)]
        while True:
            try:
                return cls.query.find_and_modify(
                    query=dict(state=state),
                    update={
                        '$set': dict(
                            state='busy',
                            process=process)
                        },
                    new=True,
                    sort=sort)
            except pymongo.errors.OperationFailure:
                if waitfunc is None:
                    return None
                waitfunc()

    @classmethod
    def timeout_tasks(cls, older_than=None):
        spec = dict(state='busy')
        if older_than:
            spec['timestamp'] = {'$lt':older_than}
        cls.query.update(spec, {'$set': dict(state='ready')}, multi=True)

    @classmethod
    def clear_complete(cls, older_than=None):
        spec = dict(state='busy')
        if older_than:
            spec['timestamp'] = {'$lt':older_than}
        cls.query.remove(spec)

    @classmethod
    def run_ready(cls, worker=None):
        '''Run all the tasks that are currently ready'''
        for task in cls.query.find(dict(state='ready')).all():
            task.process = worker
            task()

    def __call__(self):
        from allura import model as M
        log.info('%r', self)
        old_cproject = c.project
        old_capp = c.app
        old_cuser = c.user
        try:
            func = loads(self.function)
            if self.context.project_id:
                c.project = M.Project.query.get(_id=self.context.project_id)
            if self.context.app_config_id:
                app_config = M.AppConfig.query.get(_id=self.context.app_config_id)
                c.app = c.project.app_instance(app_config)
            if self.context.user_id:
                c.user = M.User.query.get(_id=self.context.user_id)
            self.result = func(*self.args, **self.kwargs)
            self.state = 'complete'
            return self.result
        except Exception:
            log.exception('%r', self)
            self.state = 'error'
            self.result = traceback.format_exc()
        finally:
            c.project = old_cproject
            c.app = old_capp
            c.user = old_cuser

    def join(self, poll_interval=0.1):
        while self.state not in ('complete', 'error'):
            time.sleep(poll_interval)
            self.query.find(dict(_id=self._id), refresh=True).first()
            print self.state,
        return self.result
