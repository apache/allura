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

from ming.orm import session
import pkg_resources

from alluratest.controller import setup_basic_test, setup_global_objects
from forgetracker.command import fix_discussion
from allura.tests.decorators import with_tracker
from allura import model as M
from forgetracker import model as TM


test_config = pkg_resources.resource_filename(
    'allura', '../test.ini') + '#main'


def setup_module(self):
    setup_basic_test()
    setup_global_objects()


@with_tracker
def break_discussion():
    """Emulate buggy 'ticket move' behavior"""
    project = M.Project.query.get(shortname='test')
    tracker = M.AppConfig.query.find({'options.mount_point': 'bugs'}).first()
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
    t.discussion_thread.add_post(text='comment 1')
    t.discussion_thread.add_post(text='comment 2')
    session(t).flush(t)


def test_fix_discussion():
    break_discussion()

    tracker = M.AppConfig.query.find({'options.mount_point': 'bugs'}).first()
    t1 = TM.Ticket.query.get(ticket_num=1)
    t2 = TM.Ticket.query.get(ticket_num=2)
    assert (
        t1.discussion_thread.discussion.app_config_id != tracker._id)
    assert t2.discussion_thread.discussion_id != tracker.discussion_id

    cmd = fix_discussion.FixDiscussion('fix-discussion')
    cmd.run([test_config, 'test'])

    t1 = TM.Ticket.query.get(ticket_num=1)
    t2 = TM.Ticket.query.get(ticket_num=2)
    assert t1.discussion_thread.discussion.app_config_id == tracker._id
    assert t2.discussion_thread.discussion_id == tracker.discussion_id
    for p in t2.discussion_thread.posts:
        assert p.app_config_id == tracker._id
        assert p.app_id == tracker._id
        assert p.discussion_id == tracker.discussion_id
