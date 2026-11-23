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

import pprint
from datetime import datetime, timedelta

from ming.odm import ThreadLocalODMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M


def setup_module():
    setup_basic_test()
    ThreadLocalODMSession.close_all()
    setup_global_objects()
    M.MonQTask.query.remove({})


def test_basic_task():
    task = M.MonQTask.post(pprint.pformat, ([5, 6],))
    ThreadLocalODMSession.flush_all()
    ThreadLocalODMSession.close_all()
    task = M.MonQTask.get()
    assert task
    task()
    assert task.result == 'I[5, 6]', task.result


def current_task_id():
    return M.MonQTask.current()._id


def reschedule_self(delay, attempts=0):
    task = M.MonQTask.current()
    task.kwargs['attempts'] = attempts + 1
    task.reschedule(delay)
    return 'rescheduled'


def test_current():
    M.MonQTask.query.remove({})
    assert M.MonQTask.current() is None
    task = M.MonQTask.post(current_task_id)
    task()
    assert task.result == task._id
    assert M.MonQTask.current() is None


def test_reschedule():
    M.MonQTask.query.remove({})
    task = M.MonQTask.post(reschedule_self, (600,))
    ThreadLocalODMSession.flush_all()
    ThreadLocalODMSession.close_all()
    task = M.MonQTask.get()
    assert task.state == 'busy'
    task()
    assert task.result == 'rescheduled'

    ThreadLocalODMSession.close_all()
    task = M.MonQTask.query.get(_id=task._id)
    assert task.state == 'ready'
    assert task.process is None
    assert task.time_queue > datetime.utcnow() + timedelta(seconds=590)
    assert task.kwargs == {'attempts': 1}
    assert M.MonQTask.get() is None


def limited_task():
    return M.MonQTask.reschedule_if_too_many_running(max_running=2) or 'ran'


def _run_limited_task_with_others_busy(*busy_start_times: datetime) -> M.MonQTask:
    M.MonQTask.query.remove({})
    for time_start in busy_start_times:
        other = M.MonQTask.post(limited_task)
        other.state = 'busy'
        other.time_start = time_start
    M.MonQTask.post(limited_task)
    ThreadLocalODMSession.flush_all()
    ThreadLocalODMSession.close_all()
    task = M.MonQTask.get()
    task()
    ThreadLocalODMSession.close_all()
    return M.MonQTask.query.get(_id=task._id)


def test_reschedule_if_too_many_running():
    now = datetime.utcnow()
    task = _run_limited_task_with_others_busy(now, now)
    assert task.state == 'ready'
    assert now + timedelta(minutes=14) < task.time_queue < now + timedelta(minutes=31)
    assert task.result.startswith('2 other allura.tests.model.test_monq.limited_task tasks are running, rescheduled')


def test_reschedule_if_too_many_running_under_limit():
    task = _run_limited_task_with_others_busy(datetime.utcnow())
    assert task.state == 'complete'
    assert task.result == 'ran'


def test_reschedule_if_too_many_running_ignores_old_busy():
    now = datetime.utcnow()
    task = _run_limited_task_with_others_busy(now, now - timedelta(hours=25))
    assert task.state == 'complete'
    assert task.result == 'ran'


def test_reschedule_if_too_many_running_outside_task():
    M.MonQTask.query.remove({})
    assert limited_task() == 'ran'


def merging_task(name):
    merged = M.MonQTask.merge_ready_tasks(limit=2)
    return [name] + [t.args[0] for t in merged]


def test_merge_ready_tasks():
    M.MonQTask.query.remove({})
    M.MonQTask.post(merging_task, ('first',))
    M.MonQTask.post(merging_task, ('second',))
    M.MonQTask.post(merging_task, ('delayed',), delay=600)
    M.MonQTask.post(merging_task, ('third',), delay=900)
    M.MonQTask.post(pprint.pformat, ('different task name',))
    ThreadLocalODMSession.flush_all()
    ThreadLocalODMSession.close_all()

    task = M.MonQTask.get(only=['allura.tests.model.test_monq.merging_task'])
    task()
    assert task.result == ['first', 'second', 'delayed']
    ThreadLocalODMSession.close_all()
    skipped = M.MonQTask.query.find({'state': 'skipped'}).all()
    assert sorted(t.args[0] for t in skipped) == ['delayed', 'second']
    assert {t.result for t in skipped} == {f'merged into task {task._id}'}
    assert M.MonQTask.query.find({'state': 'ready'}).count() == 2


def test_merge_ready_tasks_outside_task():
    M.MonQTask.query.remove({})
    M.MonQTask.post(merging_task, ('other',))
    assert merging_task('direct') == ['direct']
    assert M.MonQTask.query.find({'state': 'ready'}).count() == 1
