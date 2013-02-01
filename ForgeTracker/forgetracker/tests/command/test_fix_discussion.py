from ming.orm import session
from nose.tools import assert_equal, assert_not_equal

from alluratest.controller import setup_basic_test, setup_global_objects
from forgetracker.command import fix_discussion
from allura.tests.decorators import with_tracker
from allura import model as M
from forgetracker import model as TM

test_config = 'test.ini#main'


def setUp(self):
    """Method called by nose before running each test"""
    setup_basic_test()
    setup_global_objects()


@with_tracker
def break_discussion():
    """Emulate buggy 'ticket move' behavior"""
    project = M.Project.query.get(shortname='test')
    discussion = M.Discussion(name='fake discussion')
    app_config = M.AppConfig()
    app_config.tool_name = 'Tickets'
    app_config.project_id = project._id
    app_config.options = {'mount_point': 'fake'}
    session(app_config).flush(app_config)
    discussion.app_config_id = app_config._id
    session(discussion).flush(discussion)

    t = TM.Ticket.new()
    t.summary = 'ticket 1'
    # move disscusion somewhere
    t.discussion_thread.discussion.app_config_id = discussion.app_config_id
    session(t).flush(t)
    t = TM.Ticket.new()
    t.summary = 'ticket 2'
    # moved ticket attached to wrong discussion
    t.discussion_thread.discussion_id = discussion._id
    session(t).flush(t)

def test_fix_discussion():
    break_discussion()

    tracker = M.AppConfig.query.find({'options.mount_point': 'bugs'}).first()
    t1 = TM.Ticket.query.get(ticket_num=1)
    t2 = TM.Ticket.query.get(ticket_num=2)
    assert_not_equal(t1.discussion_thread.discussion.app_config_id, tracker._id)
    assert_not_equal(t2.discussion_thread.discussion_id, tracker.discussion_id)

    cmd = fix_discussion.FixDiscussion('fix-discussion')
    cmd.run([test_config, 'test'])

    t1 = TM.Ticket.query.get(ticket_num=1)
    t2 = TM.Ticket.query.get(ticket_num=2)
    assert_equal(t1.discussion_thread.discussion.app_config_id, tracker._id)
    assert_equal(t2.discussion_thread.discussion_id, tracker.discussion_id)
