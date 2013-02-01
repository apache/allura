from alluratest.controller import setup_basic_test, setup_global_objects
from forgetracker.command import fix_discussion

test_config = 'test.ini#main'


def setUp(self):
    """Method called by nose before running each test"""
    setup_basic_test()
    setup_global_objects()


def break_discussion():
    """Emulate buggy 'ticket move' behavior for discussion"""
    pass


def test_fix_discussion():
    break_discussion()
    cmd = fix_discussion.FixDiscussion('fix-discussion')
    cmd.run([test_config, 'project'])
