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

import tempfile
import json
import operator
import os
from io import BytesIO

from tg import tmpl_context as c
from cgi import FieldStorage

from alluratest.controller import setup_basic_test
from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.tests import decorators as td
from forgetracker import model as TM
from forgetracker.site_stats import tickets_stats_24hr
from forgetracker.tests.functional.test_root import TrackerTestController


class TestApp:

    def setup_method(self, method):
        setup_basic_test()

    @td.with_tracker
    def test_inbound_email(self):
        ticket = TM.Ticket.new()
        ticket.summary = 'test ticket'
        ticket.description = 'test description'

        # send a message with no ticket matching it
        message_id = '123@localhost'
        message = 'test message'
        msg = dict(payload=message, message_id=message_id, headers={'Subject': 'test'})
        c.app.handle_message('1', msg)
        # message gets added as a post on the ticket
        post = M.Post.query.get(_id=message_id)
        assert post["text"] == message

    @td.with_tracker
    def test_inbound_email_no_match(self):
        # send a message with no ticket matching it
        message_id = '123@localhost'
        message = 'test message'
        msg = dict(payload=message, message_id=message_id, headers={'Subject': 'test'})
        # no ticket matching it
        c.app.handle_message('6789', msg)
        # no new message
        post = M.Post.query.get(_id=message_id)
        assert post is None

    @td.with_tracker
    def test_uninstall(self):
        t = TM.Ticket.new()
        t.summary = 'new ticket'
        ThreadLocalORMSession.flush_all()
        assert TM.Ticket.query.get(summary='new ticket')
        # c.app.uninstall(c.project) errors out, but works ok in test_uninstall for repo tools.  So instead:
        c.project.uninstall_app('bugs')
        assert not TM.Ticket.query.get(summary='new ticket')

    @td.with_tracker
    def test_tickets_stats_24hr(self):
        # invoked normally via entry point
        TM.Ticket.new()
        TM.Ticket.new()
        assert 2 == tickets_stats_24hr()

    @td.with_tracker
    def test_sitemap_xml(self):
        assert [] == c.app.sitemap_xml()
        TM.Ticket.new()
        assert 1 == len(c.app.sitemap_xml())

    @td.with_tracker
    def test_sitemap_xml_ignored(self):
        TM.Ticket.new(form_fields=dict(deleted=True))
        assert [] == c.app.sitemap_xml()
        # still add to sitemap even if only tickets are closed
        TM.Ticket.new(form_fields=dict(
            status=c.app.globals.closed_status_names[0]))
        assert 1 == len(c.app.sitemap_xml())


class TestBulkExport(TrackerTestController):

    @td.with_tracker
    def setup_with_tools(self):
        super().setup_with_tools()
        self.project = M.Project.query.get(shortname='test')
        self.tracker = self.project.app_instance('bugs')
        self.new_ticket(summary='foo', _milestone='1.0')
        self.new_ticket(summary='bar', _milestone='2.0')
        self.ticket = TM.Ticket.query.find(dict(summary='foo')).first()
        self.post = self.ticket.discussion_thread.add_post(text='silly comment')
        ThreadLocalORMSession.flush_all()
        test_file1 = FieldStorage()
        test_file1.name = 'file_info'
        test_file1.filename = 'test_file'
        test_file1.file = BytesIO(b'test file1\n')
        self.post.add_attachment(test_file1)
        ThreadLocalORMSession.flush_all()

    def test_bulk_export(self):
        # Clear out some context vars, to properly simulate how this is run from the export task
        # Besides, core functionality shouldn't need the c context vars
        c.app = c.project = None

        f = tempfile.TemporaryFile('w+')
        self.tracker.bulk_export(f)
        f.seek(0)
        tracker = json.loads(f.read())

        tickets = sorted(tracker['tickets'],
                         key=operator.itemgetter('summary'))
        assert len(tickets) == 2
        ticket_foo = tickets[1]
        assert ticket_foo['summary'] == 'foo'
        assert ticket_foo['custom_fields']['_milestone'] == '1.0'
        posts_foo = ticket_foo['discussion_thread']['posts']
        assert len(posts_foo) == 1
        assert posts_foo[0]['text'] == 'silly comment'

        tracker_config = tracker['tracker_config']
        assert 'options' in list(tracker_config.keys())
        assert tracker_config['options']['mount_point'] == 'bugs'

        milestones = sorted(tracker['milestones'],
                            key=operator.itemgetter('name'))
        assert milestones[0]['name'] == '1.0'
        assert milestones[1]['name'] == '2.0'

        saved_bins_summaries = [bin['summary']
                                for bin in tracker['saved_bins']]
        assert 'Closed Tickets' in saved_bins_summaries

    def test_export_with_attachments(self):

        f = tempfile.TemporaryFile('w+')
        temp_dir = tempfile.mkdtemp()
        self.tracker.bulk_export(f, temp_dir, True)
        f.seek(0)
        tracker = json.loads(f.read())
        tickets = sorted(tracker['tickets'],
                         key=operator.itemgetter('summary'))
        file_path = os.path.join(
            'bugs',
            str(self.ticket._id),
            str(self.post.thread_id),
            self.post.slug,
            'test_file'
        )
        assert tickets[1]['discussion_thread']['posts'][0]['attachments'][0]['path'] == file_path
        os.path.exists(file_path)
