import pprint
from nose.tools import with_setup

from ming.orm import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M

def setUp():
    setup_basic_test()
    ThreadLocalORMSession.close_all()
    setup_global_objects()

@with_setup(setUp)
def test_basic_task():
    task = M.MonQTask.post(
        pprint.pformat, dict(a=5, b=6))
    print 'Created task', task
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()
    task = M.MonQTask.get()
    print 'Popped task', task
    print task()
