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
from datetime import datetime
import six.moves.urllib.request
import six.moves.urllib.parse
import six.moves.urllib.error
import os
import time
import json
from io import BytesIO
import allura
import mock

import PIL
from bs4 import BeautifulSoup
from mock import patch
from formencode.variabledecode import variable_encode
from tg import tmpl_context as c
from tg import app_globals as g
from tg import config

from allura.tests.decorators import assert_equivalent_urls
from allura.tests.test_globals import squish_spaces
from alluratest.controller import TestController, setup_basic_test
from allura import model as M
from forgewiki import model as wm
from forgetracker import model as tm

from allura.lib.security import has_access, Credentials
from allura.lib import helpers as h
from allura.lib.search import SearchError
from allura.lib.utils import urlencode
from allura.tests import decorators as td
from allura.tasks import mail_tasks
from ming.orm.ormsession import ThreadLocalORMSession
import six


def find(d, pred):
    for n, v in d.items():
        if pred(v):
            return n, v


class TrackerTestController(TestController):
    def setup_method(self, method):
        super().setup_method(method)
        self.setup_with_tools()

    @td.with_tracker
    def setup_with_tools(self):
        pass

    def _find_new_ticket_form(self, resp):
        def cond(f):
            return f.action.endswith('/save_ticket')
        return self.find_form(resp, cond)

    def _find_update_ticket_form(self, resp):
        def cond(f):
            return f.action.endswith('/update_ticket_from_widget')
        return self.find_form(resp, cond)

    def new_ticket(self, mount_point='/bugs/', extra_environ=None, **kw):
        extra_environ = extra_environ or {}
        response = self.app.get(mount_point + 'new/',
                                extra_environ=extra_environ)
        form = self._find_new_ticket_form(response)
        for k, v in kw.items():
            if isinstance(v, bool):
                form['ticket_form.%s' % k] = v
            else:
                form['ticket_form.%s' % k].force_value(v)
        resp = form.submit(extra_environ=extra_environ)
        assert resp.status_int != 200, resp
        return resp


class TestMilestones(TrackerTestController):
    def test_milestone_list(self):
        r = self.app.get('/bugs/milestones')
        assert '1.0' in r, r.showbrowser()

    def test_milestone_list_progress(self):
        self.new_ticket(summary='foo', _milestone='1.0')
        self.new_ticket(summary='bar', _milestone='1.0', status='closed')
        r = self.app.get('/bugs/milestones')
        assert '1 / 2' in r, r.showbrowser()

    def test_default_milestone_created_if_missing(self):
        p = M.Project.query.get(shortname='test')
        app = p.app_instance('bugs')
        app.globals.custom_fields = []
        ThreadLocalORMSession.flush_all()
        d = {
            'field_name': '_milestone',
            'milestones-0.old_name': '',
            'milestones-0.new_name': '1.0',
            'milestones-0.description': 'Version 1',
            'milestones-0.complete': 'Open',
            'milestones-0.due_date': ''
        }
        r = self.app.post('/bugs/update_milestones', d)
        r = self.app.get('/bugs/milestones')
        assert 'Version 1' in r
        # make sure _milestone doesn't get created again if it already exists
        r = self.app.post('/bugs/update_milestones', d)
        p = M.Project.query.get(shortname='test')
        app = p.app_instance('bugs')
        assert len(app.globals.custom_fields) == 1, len(
            app.globals.custom_fields)

    def test_closed_milestone(self):
        self.new_ticket(summary='bar', _milestone='1.0', status='closed')
        d = {
            'field_name': '_milestone',
            'milestones-0.old_name': '1.0',
            'milestones-0.new_name': '1.0',
            'milestones-0.description': '',
            'milestones-0.complete': 'Closed',
            'milestones-0.due_date': ''
        }
        self.app.post('/bugs/update_milestones', d)
        d = {
            'field_name': '_milestone',
            'milestones-9.old_name': '',
            'milestones-9.new_name': '3.0',
            'milestones-9.description': '',
            'milestones-9.complete': 'Closed',
            'milestones-9.due_date': ''
        }
        self.app.post('/bugs/update_milestones', d)
        d = {
            'field_name': '_milestone',
            'milestones-9.old_name': '',
            'milestones-9.new_name': '4.0',
            'milestones-9.description': '',
            'milestones-9.complete': 'Closed',
            'milestones-9.due_date': ''
        }
        self.app.post('/bugs/update_milestones', d)
        r = self.app.get('/bugs/1/')
        closed = r.html.find('optgroup', label='Closed')
        assert closed
        closed = str(closed)
        assert '<option selected value="1.0">1.0</option>' in r
        assert '<option selected value="1.0">1.0</option>' not in closed
        assert '<option value="2.0">2.0</option>' in r
        assert '<option value="2.0">2.0</option>' not in closed
        assert '<option value="3.0">3.0</option>' in closed
        assert '<option value="4.0">4.0</option>' in closed
        r = self.app.get('/bugs/new/')
        closed = r.html.find('optgroup', label='Closed')
        assert closed
        closed = str(closed)
        assert '<option selected value="1.0">1.0</option>' not in r
        assert '<option value="1.0">1.0</option>' in closed
        assert '<option value="2.0">2.0</option>' in r
        assert '<option value="2.0">2.0</option>' not in closed
        assert '<option value="3.0">3.0</option>' in closed
        assert '<option value="4.0">4.0</option>' in closed

    def test_duplicate_milestone(self):
        self.new_ticket(summary='bar', _milestone='1.0', status='closed')
        d = {
            'field_name': '_milestone',
            'milestones-0.old_name': '',
            'milestones-0.new_name': '1.0',
            'milestones-0.description': '',
            'milestones-0.complete': 'Closed',
            'milestones-0.due_date': ''
        }
        r = self.app.post('/bugs/update_milestones', d)
        assert 'error' in self.webflash(r)

        p = M.Project.query.get(shortname='test')
        app = p.app_instance('bugs')
        assert len(app.globals.milestone_fields[0]['milestones']) == 2

        d = {
            'field_name': '_milestone',
            'milestones-0.old_name': '2.0',
            'milestones-0.new_name': '1.0',
            'milestones-0.description': '',
            'milestones-0.complete': 'Closed',
            'milestones-0.due_date': ''
        }
        r = self.app.post('/bugs/update_milestones', d)
        assert 'error' in self.webflash(r)
        assert app.globals.milestone_fields[0]['milestones'][1]['name'] == '2.0'

    def test_default_milestone(self):
        self.new_ticket(summary='bar', _milestone='1.0', status='closed')
        d = {
            'field_name': '_milestone',
            'milestones-0.old_name': '2.0',
            'milestones-0.new_name': '2.0',
            'milestones-0.description': '',
            'milestones-0.complete': 'Open',
            'milestones-0.default': 'on',
            'milestones-0.due_date': ''
        }
        self.app.post('/bugs/update_milestones', d)
        r = self.app.get('/bugs/new/')
        assert '<option selected value="2.0">2.0</option>' in r


def post_install_create_ticket_permission(app):
    """Set to authenticated permission to create tickets but not update"""
    role = M.ProjectRole.by_name('*authenticated')._id
    create_permission = M.ACE.allow(role, 'create')
    update_permission = M.ACE.allow(role, 'update')
    acl = app.config.acl
    acl.append(create_permission)
    if update_permission in acl:
        acl.remove(update_permission)


def post_install_update_ticket_permission(app):
    """Set to anonymous permission to create and update tickets"""
    role = M.ProjectRole.by_name('*anonymous')._id
    app.config.acl.append(M.ACE.allow(role, 'create'))
    app.config.acl.append(M.ACE.allow(role, 'update'))


class TestSubprojectTrackerController(TrackerTestController):
    @td.with_tool('test/sub1', 'Tickets', 'tickets')
    def test_index_page_ticket_visibility(self):
        """Test that non-admin users can see tickets created by admins."""
        self.new_ticket(summary="my ticket", mount_point="/sub1/tickets/")
        response = self.app.get('/p/test/sub1/tickets/',
                                extra_environ=dict(username='*anonymous'))
        assert 'my ticket' in response

    @td.with_tool('test/sub1', 'Tickets', 'tickets')
    def test_search_page_ticket_visibility(self):
        """Test that non-admin users can see tickets created by admins."""
        self.new_ticket(summary="my ticket", mount_point="/sub1/tickets/")
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/sub1/tickets/search/?q=my',
                                extra_environ=dict(username='*anonymous'))
        assert 'my ticket' in response, response.showbrowser()

    @td.with_tool('test/sub1', 'Tickets', 'tickets')
    def test_deleted_ticket_visibility(self):
        """Test that admins can see deleted tickets in a subproject tracker."""
        self.new_ticket(summary='test', mount_point="/sub1/tickets/")
        self.app.post('/sub1/tickets/1/delete')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/p/test/sub1/tickets/search/',
                         params=dict(q='test', deleted='True'))
        assert '<td><a href="/p/test/sub1/tickets/1/">test' in r
        assert '<tr class=" deleted">' in r


class TestFunctionalController(TrackerTestController):
    def test_bad_ticket_number(self):
        self.app.get('/bugs/input.project_user_select', status=404)

    def test_invalid_ticket(self):
        self.app.get('/bugs/2/', status=404)

    @patch('forgetracker.tracker_main.g.director.create_activity')
    def test_activity(self, create_activity):
        self.new_ticket(summary='my ticket', description='my description')
        assert create_activity.call_count == 1
        assert create_activity.call_args[0][1] == 'created'
        create_activity.reset_mock()
        self.app.post('/bugs/1/update_ticket', {
            'summary': 'my ticket',
            'description': 'new description',
        })
        assert create_activity.call_count == 1
        assert create_activity.call_args[0][1] == 'modified'

    def test_new_ticket(self):
        summary = 'test new ticket'
        ticket_view = self.new_ticket(summary=summary).follow()
        assert summary in ticket_view
        opts = self.subscription_options(ticket_view)
        assert opts['subscribed'] is False

    def test_ticket_get_markdown(self):
        self.new_ticket(summary='my ticket', description='my description')
        response = self.app.get('/bugs/1/get_markdown')
        assert 'my description' in response

    def test_ticket_update_markdown(self):
        self.new_ticket(summary='my ticket', description='my description')
        response = self.app.get('/bugs/1/get_markdown')
        response = self.app.post(
            '/bugs/1/update_markdown',
            params={
                'text': '- [x] checkbox'})
        assert response.json['status'] == 'success'
        # anon users can't edit markdown
        response = self.app.post(
            '/bugs/1/update_markdown',
            params={
                'text': '- [x] checkbox'},
            extra_environ=dict(username='*anonymous'))
        assert response.json['status'] == 'no_permission'

    def test_labels(self):
        ticket_view = self.new_ticket(summary='summary', labels="test label").follow()
        assert '''<a href="../search?q=labels:%22test+label%22">test label (1)</a>''' in ticket_view

    def test_new_with_milestone(self):
        ticket_view = self.new_ticket(
            summary='test new with milestone', **{'_milestone': '1.0'}).follow()
        assert 'Milestone' in ticket_view
        assert '1.0' in ticket_view

    def test_milestone_count(self):
        self.new_ticket(summary='test new with milestone',
                        **{'_milestone': '1.0'})
        self.new_ticket(
            summary='test new with milestone', **{'_milestone': '1.0',
                                                  'private': True})
        r = self.app.get('/bugs/milestone_counts')
        counts = {
            'milestone_counts': [
                {'name': '1.0', 'count': 2},
                {'name': '2.0', 'count': 0}
            ]}
        assert r.text == json.dumps(counts)
        # Private tickets shouldn't be included in counts if user doesn't
        # have read access to private tickets.
        r = self.app.get('/bugs/milestone_counts',
                         extra_environ=dict(username='*anonymous'))
        counts['milestone_counts'][0]['count'] = 1
        assert r.text == json.dumps(counts)

        self.app.post('/bugs/1/delete')
        r = self.app.get('/bugs/milestone_counts')
        assert r.text == json.dumps(counts)

    def test_bin_counts(self):
        self.new_ticket(summary='test new')
        self.new_ticket(summary='test new private', private=True)
        M.MonQTask.run_ready()

        r = self.app.get('/bugs/bin_counts')
        assert r.json == {"bin_counts": [{"count": 2, "label": "Changes"},
                                         {"count": 0, "label": "Closed Tickets"},
                                         {"count": 2, "label": "Open Tickets"}]}

        """
        forgetracker.model.ticket.Globals.bin_count doesn't do a permission check like corresponding milestone_count

        # Private tickets shouldn't be included in counts if user doesn't
        # have read access to private tickets.
        r = self.app.get('/bugs/bin_counts', extra_environ=dict(username='*anonymous'))
        assert_equal(r.json, {"bin_counts": [{"count": 1, "label": "Changes"},
                                             {"count": 0, "label": "Closed Tickets"},
                                             {"count": 1, "label": "Open Tickets"}]})
        """

    def test_milestone_progress(self):
        self.new_ticket(summary='Ticket 1', **{'_milestone': '1.0'})
        self.new_ticket(summary='Ticket 2', **{'_milestone': '1.0',
                                               'status': 'closed',
                                               'private': True}).follow()
        r = self.app.get('/bugs/milestone/1.0/')
        assert '1 / 2' in r
        # Private tickets shouldn't be included in counts if user doesn't
        # have read access to private tickets.
        r = self.app.get('/bugs/milestone/1.0/',
                         extra_environ=dict(username='*anonymous'))
        assert '0 / 1' in r

    def test_new_ticket_form(self):
        response = self.app.get('/bugs/new/')
        form = self._find_new_ticket_form(response)
        form['ticket_form.summary'] = 'test new ticket form'
        form['ticket_form.description'] = 'test new ticket form description'
        response = form.submit().follow()
        assert 'test new ticket form' in response
        assert 'test new ticket form description' in response

    def test_new_ticket_prepop_from_url(self):
        response = self.app.get('/bugs/new/?summary=very buggy&description=descr&labels=label1,label2&private=true'
                                '&assigned_to=test-user&_milestone=2.0&status=pending')
        form = self._find_new_ticket_form(response)
        assert form['ticket_form.summary'].value == 'very buggy'
        assert form['ticket_form.description'].value == 'descr'
        assert form['ticket_form.labels'].value == 'label1,label2'
        assert form['ticket_form.assigned_to'].value == 'test-user'
        assert form['ticket_form._milestone'].value == '2.0'
        assert form['ticket_form.status'].value == 'pending'
        assert form['ticket_form.private'].checked is True

    def test_mass_edit(self):
        self.new_ticket(summary='First Ticket').follow()
        self.new_ticket(summary='Second Ticket').follow()
        M.MonQTask.run_ready()
        first_ticket = tm.Ticket.query.find({'summary': 'First Ticket'}).first()
        second_ticket = tm.Ticket.query.find({'summary': 'Second Ticket'}).first()
        r = self.app.get('/p/test/bugs/edit/?q=ticket')
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': [str(first_ticket._id)],
            '_milestone': '2.0',
        })
        M.MonQTask.run_ready()
        r = self.app.get('/p/test/bugs/1/')
        assert '<li><strong>Milestone</strong>: 1.0 --&gt; 2.0</li>' in r
        r = self.app.get('/p/test/bugs/2/')
        assert '<li><strong>Milestone</strong>: 1.0 --&gt; 2.0</li>' not in r
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(first_ticket._id),
                str(second_ticket._id)),
            '_milestone': '1.0',
        })
        M.MonQTask.run_ready()
        r = self.app.get('/p/test/bugs/1/')
        assert '<li><strong>Milestone</strong>: 2.0 --&gt; 1.0</li>' in r
        r = self.app.get('/p/test/bugs/2/')
        assert '<li><strong>Milestone</strong>: 2.0 --&gt; 1.0</li>' not in r

        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(first_ticket._id),
                str(second_ticket._id)),
            'status': 'accepted',
        })
        M.MonQTask.run_ready()
        r = self.app.get('/p/test/bugs/1/')
        assert '<li><strong>Status</strong>: open --&gt; accepted</li>' in r
        r = self.app.get('/p/test/bugs/2/')
        assert '<li><strong>Status</strong>: open --&gt; accepted</li>' in r

    def test_label_for_mass_edit(self):
        self.new_ticket(summary='Ticket1')
        self.new_ticket(summary='Ticket2', labels='tag1')
        self.new_ticket(summary='Ticket3', labels='tag1,tag2')
        M.MonQTask.run_ready()
        ticket1 = tm.Ticket.query.get(summary='Ticket1')
        ticket2 = tm.Ticket.query.get(summary='Ticket2')
        ticket3 = tm.Ticket.query.get(summary='Ticket3')
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(ticket1._id),
                str(ticket2._id),
                str(ticket3._id)),
            'labels': 'tag2, tag3',
        })
        M.MonQTask.run_ready()

        ticket1 = tm.Ticket.query.get(summary='Ticket1')
        ticket2 = tm.Ticket.query.get(summary='Ticket2')
        ticket3 = tm.Ticket.query.get(summary='Ticket3')
        assert ticket1.labels == ['tag2', 'tag3']
        assert ticket2.labels == ['tag1', 'tag2', 'tag3']
        assert ticket3.labels == ['tag1', 'tag2', 'tag3']
        r = self.app.get('/p/test/bugs/3/')
        assert '<li><strong>Labels</strong>: tag1, tag2 --&gt; tag1, tag2, tag3</li>' in r

    def test_mass_edit_custom_fields(self):
        params = dict(
            custom_fields=[
                dict(name='_major', label='Major', type='boolean'), ],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post(
            '/admin/bugs/set_custom_fields',
            params=variable_encode(params))
        kw = {'custom_fields._major': True}
        self.new_ticket(summary='First Custom', **kw)
        self.new_ticket(summary='Second Custom')
        M.MonQTask.run_ready()

        ticket1 = tm.Ticket.query.find({'summary': 'First Custom'}).first()
        ticket2 = tm.Ticket.query.find({'summary': 'Second Custom'}).first()
        ticket2.custom_fields._major = None
        ticket2.commit()
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(ticket1._id),
                str(ticket2._id),),
            'status': 'accepted',
            '_major': 'False'
        })
        M.MonQTask.run_ready()
        r = self.app.get('/p/test/bugs/1/')
        r.mustcontain('<li><strong>Major</strong>: True --&gt; False</li>')
        assert '<li><strong>Major</strong>: True --&gt; False</li>' in r
        r = self.app.get('/p/test/bugs/2/')
        assert '<li><strong>Major</strong>: --&gt; False</li>' in r
        ticket1 = tm.Ticket.query.find({
            'summary': 'First Custom'}).first()
        ticket2 = tm.Ticket.query.find({
            'summary': 'Second Custom'}).first()
        assert ticket1.custom_fields._major is False
        assert ticket2.custom_fields._major is False

        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(ticket1._id),
                str(ticket2._id),),
            'status': 'accepted',
            '_major': 'True'
        })
        M.MonQTask.run_ready()
        r = self.app.get('/p/test/bugs/1/')
        assert '<li><strong>Major</strong>: False --&gt; True</li>' in r
        r = self.app.get('/p/test/bugs/2/')
        assert '<li><strong>Major</strong>: False --&gt; True</li>' in r
        ticket1 = tm.Ticket.query.find({'summary': 'First Custom'}).first()
        ticket2 = tm.Ticket.query.find({'summary': 'Second Custom'}).first()
        assert ticket1.custom_fields._major is True
        assert ticket2.custom_fields._major is True

        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(ticket2._id),),
            '_major': 'False'
        })
        M.MonQTask.run_ready()
        ticket2 = tm.Ticket.query.find({
            'summary': 'Second Custom'}).first()
        assert ticket2.custom_fields._major is False
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(ticket1._id),
                str(ticket2._id),),
            'status': 'accepted',
            '_major': ''
        })
        M.MonQTask.run_ready()
        ticket1 = tm.Ticket.query.find({'summary': 'First Custom'}).first()
        ticket2 = tm.Ticket.query.find({'summary': 'Second Custom'}).first()
        assert ticket1.custom_fields._major is True
        assert ticket2.custom_fields._major is False

    def test_mass_edit_select_options_split(self):
        params = dict(
            custom_fields=[
                dict(name='_type',
                     label='Type',
                     type='select',
                     options='Bug "Feature Request"')],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post(
            '/admin/bugs/set_custom_fields',
            params=variable_encode(params))
        r = self.app.get('/p/test/bugs/edit/')
        opts = r.html.find('select', attrs={'name': '_type'})
        opts = opts.findAll('option')
        assert opts[0].get('value') == ''
        assert opts[0].getText() == 'no change'
        assert opts[1].get('value') == 'Bug'
        assert opts[1].getText() == 'Bug'
        assert opts[2].get('value') == 'Feature Request'
        assert opts[2].getText() == 'Feature Request'

    def test_mass_edit_private_field(self):
        kw = {'private': True}
        self.new_ticket(summary='First', **kw)
        self.new_ticket(summary='Second')
        M.MonQTask.run_ready()
        ticket1 = tm.Ticket.query.find({'summary': 'First'}).first()
        ticket2 = tm.Ticket.query.find({'summary': 'Second'}).first()
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(ticket1._id),
                str(ticket2._id),),
            'private': 'False',
        })
        M.MonQTask.run_ready()
        r = self.app.get('/p/test/bugs/1/')
        assert '<li><strong>Private</strong>: Yes --&gt; No</li>' in r
        r = self.app.get('/p/test/bugs/2/')
        assert '<li><strong>Private</strong>: No --&gt; Yes</li>' not in r
        ticket1 = tm.Ticket.query.find({'summary': 'First'}).first()
        ticket2 = tm.Ticket.query.find({'summary': 'Second'}).first()
        assert ticket1.private is False
        assert ticket2.private is False

        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(ticket1._id),
                str(ticket2._id),),
            'private': 'True'
        })
        M.MonQTask.run_ready()
        r = self.app.get('/p/test/bugs/1/')
        assert '<li><strong>Private</strong>: No --&gt; Yes</li>' in r
        r = self.app.get('/p/test/bugs/2/')
        assert '<li><strong>Private</strong>: No --&gt; Yes</li>' in r
        ticket1 = tm.Ticket.query.find({'summary': 'First'}).first()
        ticket2 = tm.Ticket.query.find({'summary': 'Second'}).first()
        assert ticket1.private is True
        assert ticket2.private is True

        ticket2.private = False
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(ticket1._id),
                str(ticket2._id),),
            'private': ''
        })
        M.MonQTask.run_ready()
        ticket1 = tm.Ticket.query.find({'summary': 'First'}).first()
        ticket2 = tm.Ticket.query.find({'summary': 'Second'}).first()
        assert ticket1.private is True
        assert ticket2.private is False

    def test_private_ticket(self):
        ticket_view = self.new_ticket(summary='Public Ticket').follow()
        assert '<label class="simple">Private:</label> No' in squish_spaces(ticket_view.text)
        ticket_view = self.new_ticket(summary='Private Ticket',
                                      private=True).follow()
        assert '<label class="simple">Private:</label> Yes' in squish_spaces(ticket_view.text)
        M.MonQTask.run_ready()
        # Creator sees private ticket on list page...
        index_response = self.app.get('/p/test/bugs/')
        assert '2 results' in index_response
        assert 'Public Ticket' in index_response
        assert 'Private Ticket' in index_response
        # ...and in search results.
        search_response = self.app.get('/p/test/bugs/search/?q=ticket')
        assert '2 results' in search_response
        assert 'Private Ticket' in search_response
        # Unauthorized user doesn't see private ticket on list page...
        env = dict(username='*anonymous')
        r = self.app.get('/p/test/bugs/', extra_environ=env)
        assert '1 results' in r
        assert 'Private Ticket' not in r
        # ...or in search results...
        r = self.app.get('/p/test/bugs/search/?q=ticket', extra_environ=env)
        assert '1 results' in r
        assert 'Private Ticket' not in r
        # ... or in search feed...
        r = self.app.get('/p/test/bugs/search_feed?q=ticket',
                         extra_environ=env)
        assert 'Private Ticket' not in r
        # ...and can't get to the private ticket directly.
        r = self.app.get(ticket_view.request.url, extra_environ=env)
        assert 'Private Ticket' not in r
        # ... and it doesn't appear in the feed
        r = self.app.get('/p/test/bugs/feed.atom', extra_environ=env)
        assert 'Private Ticket' not in r
        # ... or in the API ...
        self.app.get('/rest/p/test/bugs/2/', extra_environ=env, status=401)
        r = self.app.get('/rest/p/test/bugs/', extra_environ=env)
        assert 'Private Ticket' not in r

        # update private ticket
        self.app.post('/bugs/1/update_ticket_from_widget', {
            'ticket_form.summary': 'Public Ticket',
            'ticket_form.description': '',
            'ticket_form.status': 'open',
            'ticket_form._milestone': '1.0',
            'ticket_form.assigned_to': '',
            'ticket_form.labels': '',
            'ticket_form.comment': 'gotta be secret about this now',
            'ticket_form.private': 'on',
        })
        response = self.app.get('/bugs/1/')
        assert '<li><strong>private</strong>: No --&gt; Yes</li>' in response

    def test_discussion_disabled_ticket(self):
        response = self.new_ticket(summary='test discussion disabled ticket').follow()
        # New tickets will not show discussion disabled
        assert '<span class="closed">Discussion Disabled</span>' not in response

        ticket_params = {
            'ticket_form.summary': 'test discussion disabled ticket',
            'ticket_form.description': '',
            'ticket_form.status': 'open',
            'ticket_form._milestone': '1.0',
            'ticket_form.assigned_to': '',
            'ticket_form.labels': '',
            'ticket_form.comment': 'no more comments allowed',
            'ticket_form.discussion_disabled': 'on',
        }

        # Disable Discussion
        response = self.app.post('/bugs/1/update_ticket_from_widget', ticket_params).follow()
        assert '<li><strong>discussion</strong>: enabled --&gt; disabled</li>' in response
        assert '<span class="closed">Discussion Disabled</span>' in response
        assert 'edit_post_form reply' in response  # Make sure admin can still comment

        # Unauthorized user cannot comment or even see form fields
        env = dict(username='*anonymous')
        r = self.app.get('/p/test/bugs/1', extra_environ=env)
        assert 'edit_post_form reply' not in r

        # Test re-enabling discussions
        ticket_params['ticket_form.discussion_disabled'] = 'off'
        response = self.app.post('/bugs/1/update_ticket_from_widget', ticket_params).follow()
        assert '<li><strong>discussion</strong>: disabled --&gt; enabled</li>' in response
        assert '<span class="closed">Discussion Disabled</span>' not in response

        # Test solr search
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        # At this point, there is one ticket and it has discussion_disabled set to False
        r = self.app.get('/bugs/search/?q=discussion_disabled_b:False')
        assert '1 results' in r
        assert 'test discussion disabled ticket' in r

        # Set discussion_disabled to True and search again
        ticket_params['ticket_form.discussion_disabled'] = 'on'
        self.app.post('/bugs/1/update_ticket_from_widget', ticket_params)
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/bugs/search/?q=discussion_disabled_b:True')
        assert '1 results' in r
        assert 'test discussion disabled ticket' in r

        # Make sure there are no other tickets or false positives for good measure.
        r = self.app.get('/bugs/search/?q=discussion_disabled_b:False')
        assert '0 results' in r

    @td.with_tool('test', 'Tickets', 'doc-bugs')
    def test_two_trackers(self):
        summary = 'test two trackers'
        ticket_view = self.new_ticket(
            '/doc-bugs/', summary=summary, _milestone='1.0').follow()
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        assert summary in ticket_view
        index_view = self.app.get('/doc-bugs/')
        assert summary in index_view
        assert sidebar_contains(index_view, '<span>1.0</span>')
        index_view = self.app.get('/bugs/')
        assert sidebar_contains(index_view, '<span>1.0</span>')
        assert summary not in index_view

    def test_render_ticket(self):
        summary = 'test render ticket'
        ticket_view = self.new_ticket(summary=summary).follow()
        ticket_view.mustcontain(summary, 'Discussion')

    def test_render_index(self):
        admin = M.User.query.get(username='test-admin')
        anon = M.User.query.get(username="*anonymous")
        for app in M.AppConfig.query.find({'options.mount_point': 'bugs'}):
            assert has_access(app, 'create', admin)
            assert not has_access(app, 'create', anon)

        index_view = self.app.get('/bugs/')
        assert 'No open tickets found.' in index_view
        assert 'Create Ticket' in index_view

        # Make sure the 'Create Ticket' button is disabled for user without 'create' perm
        r = self.app.get('/bugs/', extra_environ=dict(username='*anonymous'))
        create_button = r.html.find('a', attrs={'href': '/p/test/bugs/new/'})
        assert create_button['class'] == ['icon', 'sidebar-disabled']

    @patch.dict('allura.lib.app_globals.config', markdown_cache_threshold='0')
    def test_cached_convert(self):
        from allura.model.session import artifact_orm_session
        # Create ticket
        params = dict(ticket_num=1,
                      app_config_id=c.app.config._id,
                      summary='test md cache',
                      description='# Test markdown cached_convert',
                      mod_date=datetime(2010, 1, 1, 1, 1, 1))
        ticket = tm.Ticket(**params)

        # Enable skip_mod_date to prevent mod_date from being set automatically when the ticket is saved.
        session = artifact_orm_session._get()
        session.skip_mod_date = True

        # This visit will cause cache to be stored on the artifact.
        # We want to make sure the 'last_updated' field isn't updated by the cache creation
        r = self.app.get('/bugs/1').follow()
        last_updated = r.html.find("span", {"id": "updated_id"}).text.strip()
        assert last_updated == '2010-01-01'

        # Make sure the cache has been saved.
        t = tm.Ticket.query.find({'_id': ticket._id}).first()
        assert '<h1 id="test-markdown-cached_convert">Test markdown cached_convert</h1>' in t.description_cache.html

    def test_ticket_diffs(self):
        self.new_ticket(summary='difftest', description='1\n2\n3\n')
        self.app.post('/bugs/1/update_ticket', {
            'summary': 'difftest',
            'description': '1\n3\n4\n',
        })
        r = self.app.get('/bugs/1/')
        assert '<span class="gd">-2</span>' in r, r.showbrowser()
        assert '<span class="gi">+4</span>' in r, r.showbrowser()

    def test_meta_comment(self):
        self.new_ticket(summary="foo")
        self.app.post('/bugs/1/update_ticket', {
            'summary': 'bar',
            'comment': 'user comment',
        })
        t = tm.Ticket.query.get(ticket_num=1)
        assert t.discussion_thread.first_post.is_meta
        assert not t.discussion_thread.last_post.is_meta

    def test_ticket_label_unlabel(self):
        summary = 'test labeling and unlabeling a ticket'
        self.new_ticket(summary=summary)
        self.app.post('/bugs/1/update_ticket', {
            'summary': 'aaa',
            'description': 'bbb',
            'status': 'ccc',
            '_milestone': '',
            'assigned_to': '',
            'labels': 'yellow,greén'.encode(),
            'comment': ''
        })
        response = self.app.get('/bugs/1/')
        assert 'yellow' in response
        assert 'greén' in response
        assert '<li><strong>labels</strong>:  --&gt; yellow, greén</li>' in response
        self.app.post('/bugs/1/update_ticket', {
            'summary': 'zzz',
            'description': 'bbb',
            'status': 'ccc',
            '_milestone': '',
            'assigned_to': '',
            'labels': 'yellow',
            'comment': ''
        })
        response = self.app.get('/bugs/1/')
        assert 'yellow' in response
        assert '<li><strong>labels</strong>: yellow, greén --&gt; yellow</li>' in response
        self.app.post('/bugs/1/update_ticket', {
            'summary': 'zzz',
            'description': 'bbb',
            'status': 'ccc',
            '_milestone': '',
            'assigned_to': '',
            'labels': '',
            'comment': ''
        })
        response = self.app.get('/bugs/1/')
        assert '<li><strong>labels</strong>: yellow --&gt; </li>' in response

    def test_new_attachment(self):
        file_name = 'test_root.py'
        file_data = open(__file__, 'rb').read()
        upload = ('attachment', file_name, file_data)
        self.new_ticket(summary='test new attachment')
        ticket_editor = self.app.post('/bugs/1/update_ticket', {
            'summary': 'zzz'
        }, upload_files=[upload]).follow()
        assert file_name in ticket_editor
        assert '<span>py</span>' not in ticket_editor
        ticket_page = self.app.get('/bugs/1/')
        diff = ticket_page.html.findAll('div', attrs={'class': 'codehilite'})
        added = diff[-1].findAll('span', attrs={'class': 'gi'})[-1]
        assert '+test_root.py' in added.getText()

    def test_delete_attachment(self):
        file_name = 'test_root.py'
        file_data = open(__file__, 'rb').read()
        upload = ('attachment', file_name, file_data)
        self.new_ticket(summary='test new attachment')
        ticket_editor = self.app.post('/bugs/1/update_ticket', {
            'summary': 'zzz'
        }, upload_files=[upload]).follow()
        assert file_name in ticket_editor, ticket_editor.showbrowser()
        req = self.app.get('/bugs/1/')
        form = self._find_update_ticket_form(req)
        file_link = BeautifulSoup(form.text).findAll('a')[2]
        assert file_link.string == file_name
        self.app.post(str(file_link['href']), {
            'delete': 'True'
        })
        ticket_page = self.app.get('/bugs/1/')
        assert '/p/test/bugs/1/attachment/test_root.py' not in ticket_page
        diff = ticket_page.html.findAll('div', attrs={'class': 'codehilite'})
        removed = diff[-1].findAll('span', attrs={'class': 'gd'})[-1]
        assert '-test_root.py' in removed.getText()

    def test_delete_attachment_from_comments(self):
        ticket_view = self.new_ticket(summary='test ticket').follow()
        for f in ticket_view.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'test comment'
        self.app.post(f['action'], params=params,
                      headers={'Referer': b'/bugs/1/'})
        r = self.app.get('/bugs/1/', dict(page='1'))
        post_link = str(r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])
        self.app.post(post_link + 'attach',
                      upload_files=[('file_info', 'test.txt', b'HiThere!')])
        r = self.app.get('/bugs/1/', dict(page='1'))
        assert '<i class="fa fa-trash-o" aria-hidden="true"></i>' in r
        r.forms[5].submit()
        r = self.app.get('/bugs/1/', dict(page='1'))
        assert '<i class="fa fa-trash-o" aria-hidden="true"></i>' not in r

    def test_new_text_attachment_content(self):
        file_name = 'test_root.py'
        file_data = open(__file__, 'rb').read()
        upload = ('attachment', file_name, file_data)
        self.new_ticket(summary='test new attachment')
        ticket_editor = self.app.post('/bugs/1/update_ticket', {
            'summary': 'zzz'
        }, upload_files=[upload]).follow()
        form = self._find_update_ticket_form(ticket_editor)
        download = self.app.get(str(BeautifulSoup(form.text).findAll('a')[2]['href']))
        assert download.body == file_data

    def test_two_attachments(self):
        file_name1 = 'test_root1.py'
        file_name2 = 'test_root2.py'
        file_data = open(__file__, 'rb').read()
        self.new_ticket(summary='test new attachment')
        ticket_editor = self.app.post('/bugs/1/update_ticket', {
            'summary': 'zzz'
        }, upload_files=[('attachment', file_name1, file_data), ('attachment', file_name2, file_data)]).follow()

        assert 'test_root1.py' in ticket_editor
        assert 'test_root2.py' in ticket_editor

    def test_new_image_attachment_content(self):
        h.set_context('test', 'bugs', neighborhood='Projects')
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(
            allura.__path__[0], 'nf', 'allura', 'images', file_name)
        file_data = open(file_path, 'rb').read()
        upload = ('attachment', file_name, file_data)
        self.new_ticket(summary='test new attachment')
        self.app.post('/bugs/1/update_ticket', {
            'summary': 'zzz'
        }, upload_files=[upload]).follow()
        ticket = tm.Ticket.query.find({'ticket_num': 1}).first()
        filename = ticket.attachments[0].filename

        uploaded = PIL.Image.open(file_path)
        r = self.app.get('/bugs/1/attachment/' + filename)
        downloaded = PIL.Image.open(BytesIO(r.body))
        assert uploaded.size == downloaded.size
        r = self.app.get('/bugs/1/attachment/' + filename + '/thumb')

        thumbnail = PIL.Image.open(BytesIO(r.body))
        assert thumbnail.size == (100, 100)

    def test_sidebar_static_page(self):
        admin = M.User.query.get(username='test-admin')
        for app in M.AppConfig.query.find({'options.mount_point': 'bugs'}):
            assert has_access(app, 'create', admin)

        response = self.app.get('/bugs/search/')
        assert 'Create Ticket' in response
        assert 'Related Pages' not in response

    def test_related_artifacts(self):
        summary = 'test sidebar logic for a ticket page'
        self.new_ticket(summary=summary)
        response = self.app.get('/p/test/bugs/1/')
        assert 'Related Pages' not in response
        self.app.post('/wiki/aaa/update', params={
            'title': 'aaa',
            'text': '',
            'labels': '',
        })
        self.new_ticket(summary='bbb')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()

        h.set_context('test', 'wiki', neighborhood='Projects')
        a = wm.Page.query.find(dict(title='aaa')).first()
        a.text = '\n[bugs:#1]\n[bugs:#2]\n'
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        b = tm.Ticket.query.find(dict(ticket_num=2)).first()
        b.description = '\n[#1]\n'
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()

        response = self.app.get('/p/test/bugs/1/')
        assert 'Related' in response
        assert 'Wiki: aaa' in response
        assert 'Tickets: #2' in response

        b = tm.Ticket.query.find(dict(ticket_num=2)).first()
        b.deleted = True
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/bugs/1/')
        assert 'Tickets: #2' not in response
        response = self.app.get('/wiki/aaa/')
        assert 'alink notfound' in response

    def test_related_artifacts_closed_tickets(self):
        self.new_ticket(summary='Ticket 1')
        self.new_ticket(summary='Ticket 2', status='closed')
        self.new_ticket(summary='Ticket 3', description='[#1]\n\n[#2]')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/p/test/bugs/3/')
        assert 'Tickets: #1' in r
        assert 'Tickets: <s>#1</s>' not in r
        assert 'Tickets: <s>#2</s>' in r

        assert '<a class="alink" href="/p/test/bugs/1/">[#1]</a>' in r.text
        assert '<a class="alink strikethrough" href="/p/test/bugs/2/">[#2]</a>' in r.text

    def test_ticket_view_editable(self):
        summary = 'test ticket view page can be edited'
        self.new_ticket(summary=summary)
        response = self.app.get('/p/test/bugs/1/')
        assert response.html.find('input', {'name': 'ticket_form.summary'})
        assert response.html.find('select', {'name': 'ticket_form.assigned_to'})
        assert response.html.find('textarea', {'name': 'ticket_form.description'})
        assert response.html.find('select', {'name': 'ticket_form.status'})
        assert response.html.find('select', {'name': 'ticket_form._milestone'})
        assert response.html.find('input', {'name': 'ticket_form.labels'})
        assert response.html.find('textarea', {'name': 'ticket_form.comment'})

    def test_assigned_to_nobody(self):
        summary = 'test default assignment'
        self.new_ticket(summary=summary)
        response = self.app.get('/p/test/bugs/1/')
        assert 'nobody' in str(response.html.find('div', {'class': 'grid-5 ticket-assigned-to'}))

    def test_assign_ticket(self):
        summary = 'test assign ticket'
        self.new_ticket(summary=summary)
        response = self.app.get('/p/test/bugs/1/')
        assert 'nobody' in str(response.html.find('div', {'class': 'grid-5 ticket-assigned-to'}))
        response = self.app.post('/bugs/1/update_ticket', {
            'summary': 'zzz',
            'description': 'bbb',
            'status': 'ccc',
            '_milestone': '',
            'assigned_to': 'test-admin',
            'labels': '',
            'comment': ''
        }).follow()
        assert 'test-admin' in str(response.html.find('div',
                                                      {'class': 'grid-5 ticket-assigned-to'}))
        assert '<li><strong>summary</strong>: test assign ticket --&gt; zzz' in response
        assert '<li><strong>status</strong>: open --&gt; ccc' in response

    def test_custom_fields(self):
        params = dict(
            custom_fields=[
                dict(name='_priority', label='Priority', type='select',
                     options='normal urgent critical'),
                dict(name='_category', label='Category', type='string',
                     options=''),
                dict(name='_code_review', label='Code Review', type='user')],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post(
            '/admin/bugs/set_custom_fields',
            params=variable_encode(params))
        kw = {'custom_fields._priority': 'normal',
              'custom_fields._category': 'helloworld',
              'custom_fields._code_review': 'test-admin'}
        ticket_view = self.new_ticket(summary='test custom fields', **kw).follow()
        assert 'Priority:' in ticket_view
        assert 'normal' in ticket_view
        assert 'Test Admin' in ticket_view

    def test_select_custom_field(self):
        params = dict(
            custom_fields=[
                dict(name='_testselect', label='Test', type='select',
                     options='"test select"'),
            ],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post(
            '/admin/bugs/set_custom_fields',
            params=variable_encode(params))
        r = self.app.get('/bugs/new/')
        assert '<option value="test select">test select</option>' in r
        kw = {'custom_fields._testselect': 'test select'}
        ticket_view = self.new_ticket(summary='test select custom fields', **kw).follow()
        assert '<option selected value="test select">test select</option>' in ticket_view

    def test_select_custom_field_unicode(self):
        params = dict(
            custom_fields=[
                dict(name='_testselect', label='Test', type='select',
                     options='oné "one and á half" two'.encode()),
            ],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post(
            '/admin/bugs/set_custom_fields',
            params=variable_encode(params))
        r = self.app.get('/bugs/new/')

        r.mustcontain('<option value="oné">oné</option>')
        assert '<option value="oné">oné</option>' in r.text
        assert '<option value="one and á half">one and á half</option>' in r.text
        assert '<option value="two">two</option>' in r.text

    def test_select_custom_field_invalid_quotes(self):
        params = dict(
            custom_fields=[
                dict(name='_testselect', label='Test', type='select',
                     options='closéd "quote missing'.encode()),
            ],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post(
            '/admin/bugs/set_custom_fields',
            params=variable_encode(params))
        r = self.app.get('/bugs/new/')
        assert '<option value="closéd">closéd</option>'.encode() in r
        assert '<option value="quote">quote</option>' in r
        assert '<option value="missing">missing</option>' in r

    def test_custom_field_update_comments(self):
        params = dict(
            custom_fields=[
                dict(label='Number', type='number', options='')],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post('/admin/bugs/set_custom_fields',
                      params=variable_encode(params))
        kw = {'custom_fields._number': ''}
        ticket_view = self.new_ticket(summary='test custom fields', **kw).follow()
        assert '<strong>Number</strong>:  --&gt;' not in ticket_view
        ticket_view = self.app.post('/bugs/1/update_ticket', params={
            'summary': 'zzz',
            'description': 'bbb',
            'status': 'ccc',
            '_milestone': 'aaa',
            'assigned_to': '',
            'labels': '',
            'custom_fields._number': '',
            'comment': ''
        }).follow()
        assert '<strong>Number</strong>:  --&gt;' not in ticket_view
        ticket_view = self.app.post('/bugs/1/update_ticket', params={
            'summary': 'zzz',
            'description': 'bbb',
            'status': 'ccc',
            '_milestone': 'aaa',
            'assigned_to': '',
            'labels': '',
            'custom_fields._number': '4',
            'comment': ''
        }).follow()
        assert '<strong>Number</strong>:  --&gt;' in ticket_view

    def test_milestone_names(self):
        params = {
            'open_status_names': 'aa bb',
            'closed_status_names': 'cc',
            'custom_fields': [dict(
                label='Milestone',
                show_in_search='on',
                type='milestone',
                milestones=[
                    dict(name='aaaé'.encode()),
                    dict(name='bbb'),
                    dict(name='ccc')])]}
        self.app.post('/admin/bugs/set_custom_fields',
                      variable_encode(params),
                      status=302)
        self.new_ticket(summary='test milestone names')
        self.app.post('/bugs/1/update_ticket', {
            'summary': 'zzz',
            'description': 'bbb',
            'status': 'ccc',
            '_milestone': 'aaaé'.encode(),
            'assigned_to': '',
            'labels': '',
            'comment': ''
        })
        ticket_view = self.app.get('/p/test/bugs/1/')
        assert 'Milestone' in ticket_view
        assert 'aaaé' in ticket_view

    def test_milestone_rename(self):
        self.new_ticket(summary='test milestone rename')
        self.app.post('/bugs/1/update_ticket', {
            'summary': 'test milestone rename',
            'description': '',
            'status': '',
            '_milestone': '1.0',
            'assigned_to': '',
            'labels': '',
            'comment': ''
        })
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        ticket_view = self.app.get('/p/test/bugs/1/')
        assert 'Milestone' in ticket_view
        assert '1.0' in ticket_view
        assert 'zzzé' not in ticket_view
        self.app.post('/bugs/update_milestones', {
            'field_name': '_milestone',
            'milestones-0.old_name': '1.0',
            'milestones-0.new_name': 'zzzé'.encode(),
            'milestones-0.description': '',
            'milestones-0.complete': 'Open',
            'milestones-0.due_date': ''
        })
        ticket_view = self.app.get('/p/test/bugs/1/')
        assert '1.0' not in ticket_view
        assert 'zzzé' in ticket_view

    def test_milestone_close(self):
        self.new_ticket(summary='test milestone close')
        r = self.app.get('/bugs/milestones')
        assert 'view closed' not in r
        r = self.app.post('/bugs/update_milestones', {
            'field_name': '_milestone',
            'milestones-0.old_name': '1.0',
            'milestones-0.new_name': '1.0',
            'milestones-0.description': '',
            'milestones-0.complete': 'Closed',
            'milestones-0.due_date': ''
        })
        r = self.app.get('/bugs/milestones')
        assert 'view closed' in r

    def test_edit_all_button(self):
        admin = M.User.query.get(username='test-admin')
        for app in M.AppConfig.query.find({'options.mount_point': 'bugs'}):
            assert has_access(app, 'update', admin)

        response = self.app.get('/p/test/bugs/search/')
        assert 'Edit All' not in response

    def test_custom_fields_preserve_user_input_on_form_errors(self):
        params = dict(
            custom_fields=[
                dict(name='_priority', label='Priority', type='select',
                     options='normal urgent critical'),
                dict(name='_category', label='Category', type='string',
                     options='')],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post(
            '/admin/bugs/set_custom_fields', params=variable_encode(params))
        # Test new ticket form
        r = self.app.get('/bugs/new/')
        form = self._find_new_ticket_form(r)
        form['ticket_form.custom_fields._priority'] = 'urgent'
        form['ticket_form.custom_fields._category'] = 'bugs'
        error_form = form.submit()
        form = self._find_new_ticket_form(error_form)
        assert form['ticket_form.custom_fields._priority'].value == 'urgent'
        assert form['ticket_form.custom_fields._category'].value == 'bugs'
        # Test edit ticket form
        self.new_ticket(summary='Test ticket')
        response = self.app.get('/bugs/1/')
        form = self._find_update_ticket_form(response)
        assert (
            form['ticket_form.custom_fields._priority'].value == 'normal')
        assert form['ticket_form.custom_fields._category'].value == ''
        form['ticket_form.summary'] = ''
        form['ticket_form.custom_fields._priority'] = 'urgent'
        form['ticket_form.custom_fields._category'] = 'bugs'
        error_form = form.submit()
        form = self._find_update_ticket_form(error_form)
        assert form['ticket_form.custom_fields._priority'].value == 'urgent'
        assert form['ticket_form.custom_fields._category'].value == 'bugs'

    def test_new_ticket_validation(self):
        summary = 'ticket summary'
        response = self.app.get('/bugs/new/')
        assert not response.html.find('div', {'class': 'error'})
        form = self._find_new_ticket_form(response)
        form['ticket_form.labels'] = 'foo'
        # try submitting with no summary set and check for error message
        error_form = form.submit()
        form = self._find_new_ticket_form(error_form)
        assert form['ticket_form.labels'].value == 'foo'
        error_message = BeautifulSoup(form.text).find('div', {'class': 'error'})
        assert error_message
        assert (error_message.string == 'You must provide a Title' or
                error_message.string == 'Missing value')
        assert error_message.findPreviousSibling('input').get('name') == 'ticket_form.summary'
        # set a summary, submit, and check for success
        form['ticket_form.summary'] = summary
        success = form.submit().follow().html
        assert success.findAll('form', {'action': '/p/test/bugs/1/update_ticket_from_widget'}) is not None
        assert success.find('input', {'name': 'ticket_form.summary'})['value'] == summary

    def test_edit_ticket_validation(self):
        old_summary = 'edit ticket test'
        new_summary = "new summary"
        self.new_ticket(summary=old_summary)
        response = self.app.get('/bugs/1/')
        # check that existing form is valid
        assert response.html.find('input', {'name': 'ticket_form.summary'})['value'] == old_summary
        assert not response.html.find('div', {'class': 'error'})
        form = self._find_update_ticket_form(response)
        # try submitting with no summary set and check for error message
        form['ticket_form.summary'] = ""
        error_form = form.submit()
        error_message = error_form.html.find('div', {'class': 'error'})
        assert error_message
        assert error_message.string == 'You must provide a Title'
        assert error_message.findPreviousSibling('input').get('name') == 'ticket_form.summary'
        # set a summary, submit, and check for success
        form = self._find_update_ticket_form(error_form)
        form['ticket_form.summary'] = new_summary
        r = form.submit()
        assert r.status_int == 302, r.showbrowser()
        success = r.follow().html
        assert success.findAll('form', {'action': '/p/test/bugs/1/update_ticket_from_widget'}) is not None
        assert success.find('input', {'name': 'ticket_form.summary'})['value'] == new_summary

    def test_home(self):
        self.new_ticket(summary='test first ticket')
        self.new_ticket(summary='test second ticket')
        self.new_ticket(summary='test third ticket')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/bugs/')
        assert 'test third ticket' in response

    def test_search(self):
        self.new_ticket(summary='test first ticket')
        self.new_ticket(summary='test second ticket')
        self.new_ticket(summary='test third ticket')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/bugs/search/?q=test&limit=2')
        response.mustcontain('canonical')
        response.mustcontain('results of 3')
        response.mustcontain('test second ticket')
        next_page_link = response.html.select('.page_list a')[0]
        assert next_page_link.text == '2'
        # keep 'q' and zero-based page nums:
        assert next_page_link['href'] == '/p/test/bugs/search/?q=test&limit=2&page=1'

        # 'filter' is special kwarg, don't let it cause problems
        r = self.app.get('/p/test/bugs/search/?q=test&filter=blah')

    def test_search_canonical(self):
        self.new_ticket(summary='test first ticket')
        self.new_ticket(summary='test second ticket')
        self.new_ticket(summary='test third ticket')
        self.new_ticket(summary='test fourth ticket')
        self.new_ticket(summary='test fifth ticket')
        self.new_ticket(summary='test sixth ticket')
        self.new_ticket(summary='test seventh ticket')
        self.new_ticket(summary='test eighth ticket')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/bugs/search/?q=test&limit=1')
        canonical = response.html.select_one('link[rel=canonical]')
        assert 'limit=2' not in canonical['href']
        response = self.app.get('/p/test/bugs/search/?q=test&limit=2&page=2')
        next = response.html.select_one('link[rel=next]')
        assert 'page=3' in next['href']
        prev = response.html.select_one('link[rel=prev]')
        assert 'page=1' in prev['href']
        response = self.app.get('/p/test/bugs/search/?q=test&limit=2&page=0')
        canonical = response.html.select_one('link[rel=canonical]')
        assert 'page=' not in canonical

    def test_search_with_strange_chars(self):
        r = self.app.get('/p/test/bugs/search/?' +
                         urlencode({'q': 'tést'}))
        assert 'Search bugs: tést' in r

    def test_saved_search_with_strange_chars(self):
        '''Sidebar must be visible even with a strange characters in saved search terms'''
        r = self.app.post('/admin/bugs/bins/save_bin', {
            'summary': 'Strange chars in terms here',
            'terms': 'labels:tést'.encode(),
            'old_summary': '',
            'sort': ''}).follow()
        r = self.app.get('/bugs/')
        assert sidebar_contains(r, 'Strange chars in terms here')

    def test_search_feed(self):
        self.new_ticket(summary='test first ticket')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        for ext in ['', '.rss', '.atom']:
            assert '<title>test first ticket</title>' in \
                   self.app.get('/p/test/bugs/search_feed%s/?q=test' % ext)

    def test_search_current_user(self):
        self.new_ticket(summary='test first ticket')
        self.new_ticket(summary='test second ticket')
        p = M.Project.query.get(shortname='test')
        p.app_instance('bugs')
        t = tm.Ticket.query.get(summary='test first ticket')
        t.reported_by_id = M.User.by_username('test-user-0')._id
        t = tm.Ticket.query.get(summary='test second ticket')
        t.reported_by_id = M.User.by_username('test-user-1')._id
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/bugs/search/?q=reported_by_s:$USER',
                                extra_environ={'username': 'test-user-0'})
        assert '1 result' in response, response.showbrowser()
        assert 'test first ticket' in response, response.showbrowser()
        response = self.app.get('/p/test/bugs/search/?q=reported_by_s:$USER',
                                extra_environ={'username': 'test-user-1'})
        assert '1 result' in response, response.showbrowser()
        assert 'test second ticket' in response, response.showbrowser()

    def test_feed(self):
        self.new_ticket(
            summary='test first ticket',
            description='test description')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/bugs/feed')
        assert 'test first ticket' in response

    def test_touch(self):
        self.new_ticket(summary='test touch')
        h.set_context('test', 'bugs', neighborhood='Projects')
        ticket = tm.Ticket.query.get(ticket_num=1)
        old_date = ticket.mod_date
        ticket.summary = 'changing the summary'
        time.sleep(1)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        ticket = tm.Ticket.query.get(ticket_num=1)
        new_date = ticket.mod_date
        assert new_date > old_date

    @patch('forgetracker.tracker_main.search_artifact')
    def test_save_invalid_search(self, search_artifact):
        err = 'Error running search query: [Reason: undefined field label]'
        search_artifact.side_effect = SearchError(err)
        r = self.app.post('/admin/bugs/bins/save_bin', {
            'summary': 'This is not too long.',
            'terms': 'label:foo',
            'old_summary': '',
            'sort': ''})
        assert err in r
        r = self.app.get('/admin/bugs/bins/')
        edit_form = r.forms['saved-search-form']
        edit_form['bins-2.summary'] = 'Original'
        edit_form['bins-2.terms'] = 'label:foo'
        r = edit_form.submit()
        assert err in r

    def test_saved_search_labels_truncated(self):
        r = self.app.post('/admin/bugs/bins/save_bin', {
            'summary': 'This is not too long.',
            'terms': 'aaa',
            'old_summary': '',
            'sort': ''}).follow()
        r = self.app.get('/bugs/')
        assert sidebar_contains(r, 'This is not too long.')
        self.app.post('/admin/bugs/bins/save_bin', {
            'summary': 'This will be truncated because it is too long to show in the sidebar without being ridiculous',
            'terms': 'aaa',
            'old_summary': '',
            'sort': ''}).follow()
        r = self.app.get('/bugs/')
        assert sidebar_contains(r, 'This will be truncated because it is too long to show in the sidebar ...')

    def test_edit_saved_search(self):
        r = self.app.get('/admin/bugs/bins/')
        edit_form = r.forms['saved-search-form']
        edit_form['bins-2.summary'] = 'Original'
        edit_form['bins-2.terms'] = 'aaa'
        edit_form.submit()
        r = self.app.get('/bugs/')
        assert sidebar_contains(r, 'Original')
        assert not sidebar_contains(r, 'New')
        r = self.app.get('/admin/bugs/bins/')
        edit_form = r.forms['saved-search-form']
        edit_form['bins-2.summary'] = 'New'
        edit_form.submit()
        r = self.app.get('/bugs/')
        assert sidebar_contains(r, 'New')
        assert not sidebar_contains(r, 'Original')

    def test_comment_split(self):
        summary = 'new ticket'
        ticket_view = self.new_ticket(summary=summary).follow()
        for f in ticket_view.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        post_content = 'ticket discussion post content'
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = post_content
        r = self.app.post(f['action'], params=params,
                          headers={'Referer': b'/bugs/1/'})
        r = self.app.get('/bugs/1/', dict(page='1'))
        assert post_content in r
        assert len(r.html.findAll(attrs={'class': 'discussion-post'})) == 1

        new_summary = 'old ticket'
        for f in ticket_view.html.findAll('form'):
            if f.get('action', '').endswith('update_ticket_from_widget'):
                break
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params['ticket_form.summary'] = new_summary
        r = self.app.post(f['action'], params=params,
                          headers={'Referer': b'/bugs/1/'})
        r = self.app.get('/bugs/1/', dict(page='1'))
        assert summary + ' --&gt; ' + new_summary in r
        assert len(r.html.findAll(attrs={'class': 'discussion-post meta_post'})) == 1

    def test_discussion_paging(self):
        summary = 'test discussion paging'
        ticket_view = self.new_ticket(summary=summary).follow()
        for f in ticket_view.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        post_content = 'ticket discussion post content'
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = post_content
        r = self.app.post(f['action'], params=params,
                          headers={'Referer': b'/bugs/1/'})
        r = self.app.get('/bugs/1/', dict(page='-1'))
        assert summary in r
        r = self.app.get('/bugs/1/', dict(page='1'))
        assert post_content in r
        # no pager if just one page
        assert 'Page 1 of 1' not in r
        # add some more posts and check for pager
        for i in range(2):
            r = self.app.post(f['action'], params=params,
                              headers={'Referer': b'/bugs/1/'})
        r = self.app.get('/bugs/1/', dict(page='1', limit='2'))
        assert 'Page 2 of 2' in r

    def test_discussion_feed(self):
        summary = 'test discussion paging'
        ticket_view = self.new_ticket(summary=summary).follow()
        for f in ticket_view.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        post_content = 'ticket discussion post content'
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = post_content
        self.app.post(f['action'], params=params,
                      headers={'Referer': b'/bugs/1/'})
        r = self.app.get('/bugs/feed.rss')
        post = M.Post.query.find().first()
        assert '/p/test/bugs/1/?limit=25#' + post.slug in r
        r = self.app.get('/bugs/1/')
        post_link = str(r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])
        post_form = r.html.find('form', {'action': post_link + 'reply'})
        params = dict()
        inputs = post_form.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[post_form.find('textarea')['name']] = 'Tis a reply'
        r = self.app.post(post_link + 'reply',
                          params=params,
                          headers={'Referer': post_link.encode("utf-8")})
        r = self.app.get('/bugs/feed.rss')
        assert 'Tis a reply' in r
        assert 'ticket discussion post content' in r
        r = self.app.get('/bugs/1/feed.rss')
        assert 'Tis a reply' in r
        assert 'ticket discussion post content' in r

    def test_bulk_edit_index(self):
        self.new_ticket(summary='test first ticket', status='open')
        self.new_ticket(summary='test second ticket', status='accepted')
        self.new_ticket(summary='test third ticket', status='closed')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/bugs/?sort=summary+asc')
        ticket_rows = response.html.find('table', {'class': 'ticket-list'}).find('tbody')
        assert 'test first ticket' in ticket_rows.text
        assert 'test second ticket' in ticket_rows.text
        edit_link = response.html.find('a', {'title': 'Bulk Edit'})
        expected_link = "/p/test/bugs/edit/?q=%21status%3Aclosed+%26%26+%21status%3Awont-fix"\
                        "&sort=snippet_s+asc&limit=25&filter=&page=0"
        assert_equivalent_urls(expected_link, edit_link['href'])
        response = self.app.get(edit_link['href'])
        ticket_rows = response.html.find('tbody', {'class': 'ticket-list'})
        assert 'test first ticket' in ticket_rows.text
        assert 'test second ticket' in ticket_rows.text

    def test_bulk_edit_milestone(self):
        self.new_ticket(summary='test first ticket',
                        status='open', _milestone='1.0')
        self.new_ticket(summary='test second ticket',
                        status='accepted', _milestone='1.0')
        self.new_ticket(summary='test third ticket',
                        status='closed', _milestone='1.0')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/bugs/milestone/1.0/?sort=ticket_num+asc')
        ticket_rows = response.html.find('table', {'class': 'ticket-list'}).find('tbody')
        assert 'test first ticket' in ticket_rows.text
        assert 'test second ticket' in ticket_rows.text
        assert 'test third ticket' in ticket_rows.text
        edit_link = response.html.find('a', {'title': 'Bulk Edit'})
        expected_link = "/p/test/bugs/edit/?q=_milestone%3A1.0&sort=ticket_num_i+asc&limit=25&filter=&page=0"
        assert_equivalent_urls(expected_link, edit_link['href'])
        response = self.app.get(edit_link['href'])
        ticket_rows = response.html.find('tbody', {'class': 'ticket-list'})
        assert 'test first ticket' in ticket_rows.text
        assert 'test second ticket' in ticket_rows.text
        assert 'test third ticket' in ticket_rows.text

    def test_bulk_edit_search(self):
        self.new_ticket(summary='test first ticket', status='open')
        self.new_ticket(summary='test second ticket', status='open')
        self.new_ticket(summary='test third ticket', status='closed', _milestone='1.0')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/bugs/search/?q=status%3Aopen')
        ticket_rows = response.html.find('table', {'class': 'ticket-list'}).find('tbody')
        assert 'test first ticket' in ticket_rows.text
        assert 'test second ticket' in ticket_rows.text
        assert 'test third ticket' not in ticket_rows.text
        edit_link = response.html.find('a', {'title': 'Bulk Edit'})
        expected_link = "/p/test/bugs/edit/?q=status%3Aopen&limit=25&filter=%7B%7D&page=0"
        assert_equivalent_urls(expected_link, edit_link['href'])
        response = self.app.get(edit_link['href'])
        ticket_rows = response.html.find('tbody', {'class': 'ticket-list'})
        assert 'test first ticket' in ticket_rows.text
        assert 'test second ticket' in ticket_rows.text
        assert 'test third ticket' not in ticket_rows.text

    def test_bulk_edit_after_filtering(self):
        self.new_ticket(summary='test first ticket', status='open')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        self.app.get("/p/test/bugs/edit/?q=test&limit=25&sort=&page=0&filter={'status'%3A+['open']}")

    def test_new_ticket_notification_contains_attachments(self):
        file_name = 'tést_root.py'.encode()
        file_data = open(__file__, 'rb').read()
        upload = ('ticket_form.attachment', file_name, file_data)
        r = self.app.post('/bugs/save_ticket', {
            'ticket_form.summary': 'new ticket with attachment'
        }, upload_files=[upload]).follow()
        assert file_name in r
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        email = M.MonQTask.query.find(
            dict(task_name='allura.tasks.mail_tasks.sendmail')
        ).first()
        expected_text = (
            '**Attachments:**\n\n'
            '- [tést_root.py]'
            '(http://localhost/p/test/bugs/1/attachment/t%C3%A9st_root.py)')
        assert expected_text in email.kwargs['text']

    def test_ticket_notification_contains_milestones(self):
        params = dict(
            custom_fields=[
                dict(
                    name='_releases',
                    label='Releases',
                    type='milestone',
                    milestones=[{'name': '0.9.3'}, {'name': '1.0-beta'}],
                    show_in_search='on',
                ),
                dict(
                    name='_milestone',
                    label='Milestone',
                    type='milestone',
                    milestones=[{'name': '1.0'}, {'name': '2.0'}],
                    show_in_search='on',
                ),
            ],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post('/admin/bugs/set_custom_fields',
                      params=variable_encode(params))
        self.new_ticket(summary='test new milestone', _milestone='2.0',
                        **{'custom_fields._releases': '1.0-beta'})
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        email = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).first()
        assert '**Releases:** 1.0-beta' in email.kwargs.text
        assert '**Milestone:** 2.0' in email.kwargs.text

    def test_bulk_edit_notifications(self):
        self.new_ticket(summary='test first ticket',
                        status='open', _milestone='2.0')
        self.new_ticket(summary='test second ticket',
                        status='accepted', _milestone='1.0')
        self.new_ticket(summary='test third ticket', status='unread')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        first_ticket = tm.Ticket.query.get(summary='test first ticket')
        second_ticket = tm.Ticket.query.get(summary='test second ticket')
        third_ticket = tm.Ticket.query.get(summary='test third ticket')
        first_user = M.User.by_username('test-user-0')
        second_user = M.User.by_username('test-user-1')
        admin = M.User.by_username('test-admin')
        first_ticket.subscribe(user=first_user)
        second_ticket.subscribe(user=second_user)
        M.MonQTask.query.remove()
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(first_ticket._id),
                str(second_ticket._id),
                str(third_ticket._id)),
            'status': 'accepted',
            '_milestone': '2.0',
            'assigned_to': 'test-admin'})
        M.MonQTask.run_ready()

        emails = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).all()
        assert len(emails) == 3
        for email in emails:
            assert email.kwargs.subject == '[test:bugs] Mass edit changes by Test Admin'
        first_user_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(first_user._id)
        }).all()
        assert len(first_user_email) == 1
        first_user_email = first_user_email[0]
        second_user_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(second_user._id)
        }).all()
        assert len(second_user_email) == 1
        second_user_email = second_user_email[0]
        admin_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(admin._id)
        }).all()
        assert len(admin_email) == 1
        admin_email = admin_email[0]

        # Expected data
        email_header = '''Mass edit changing:

- **Owner**: Test Admin
- **Status**: accepted
- **Milestone**: 2.0

'''
        first_ticket_changes = '''ticket: bugs:#1 test first ticket

- **Owner**: Anonymous --> Test Admin
- **Status**: open --> accepted
'''
        second_ticket_changes = '''ticket: bugs:#2 test second ticket

- **Owner**: Anonymous --> Test Admin
- **Milestone**: 1.0 --> 2.0
'''
        third_ticket_changes = '''ticket: bugs:#3 test third ticket

- **Owner**: Anonymous --> Test Admin
- **Status**: unread --> accepted
- **Milestone**: 1.0 --> 2.0
'''
        email = '\n'.join([email_header, first_ticket_changes, ''])
        assert email == first_user_email.kwargs.text
        email = '\n'.join([email_header, second_ticket_changes, ''])
        assert email == second_user_email.kwargs.text
        assert email_header in admin_email.kwargs.text
        assert first_ticket_changes in admin_email.kwargs.text
        assert second_ticket_changes in admin_email.kwargs.text
        assert third_ticket_changes in admin_email.kwargs.text

    def test_bulk_edit_notifications_monitoring_email(self):
        self.app.post('/admin/bugs/set_options', params={
            'TicketMonitoringEmail': 'monitoring@email.com',
            'TicketMonitoringType': 'AllTicketChanges',
        })
        self.new_ticket(summary='test first ticket',
                        status='open', _milestone='2.0', private=True)
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        ticket = tm.Ticket.query.get(summary='test first ticket')
        M.MonQTask.query.remove()
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': [str(ticket._id)],
            'status': 'accepted'})
        M.MonQTask.run_ready()
        emails = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).all()
        # one for admin and one for monitoring email
        assert len(emails) == 2
        for email in emails:
            assert email.kwargs.subject == '[test:bugs] Mass edit changes by Test Admin'
        admin = M.User.by_username('test-admin')
        admin_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(admin._id)
        }).all()
        monitoring_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': 'monitoring@email.com'
        }).all()
        assert len(admin_email) == 1
        assert len(monitoring_email) == 1
        admin_email_text = admin_email[0].kwargs.text
        monitoring_email_text = monitoring_email[0].kwargs.text
        assert admin_email_text == monitoring_email_text

    def test_bulk_edit_notifications_monitoring_email_public_only(self):
        """Test that private tickets are not included in bulk edit
        notifications if the "public only" option is selected.
        """
        self.app.post('/admin/bugs/set_options', params={
            'TicketMonitoringEmail': 'monitoring@email.com',
            'TicketMonitoringType': 'AllPublicTicketChanges',
        })
        self.new_ticket(summary='test first ticket', status='open', _milestone='2.0')
        self.new_ticket(summary='test second ticket', status='open', private=True)
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        tickets = tm.Ticket.query.find(dict(status='open')).all()
        M.MonQTask.query.remove()
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': [str(t._id) for t in tickets],
            'status': 'accepted'})
        M.MonQTask.run_ready()
        emails = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).all()
        # one for admin and one for monitoring email
        assert len(emails) == 2
        for email in emails:
            assert email.kwargs.subject == '[test:bugs] Mass edit changes by Test Admin'
        admin = M.User.by_username('test-admin')
        admin_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(admin._id)
        }).all()
        monitoring_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': 'monitoring@email.com'
        }).all()
        assert len(admin_email) == 1
        assert len(monitoring_email) == 1
        admin_email_text = admin_email[0].kwargs.text
        monitoring_email_text = monitoring_email[0].kwargs.text
        assert 'second ticket' in admin_email_text
        assert 'second ticket' not in monitoring_email_text

    def test_bulk_edit_monitoring_email_all_private_edits(self):
        """Test that no monitoring email is sent if the "public only"
        option is selected, and only private tickets were updated.
        """
        self.app.post('/admin/bugs/set_options', params={
            'TicketMonitoringEmail': 'monitoring@email.com',
            'TicketMonitoringType': 'AllPublicTicketChanges',
        })
        self.new_ticket(summary='test first ticket', status='open', private=True)
        self.new_ticket(summary='test second ticket', status='open', private=True)
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        tickets = tm.Ticket.query.find(dict(status='open')).all()
        M.MonQTask.query.remove()
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': [str(t._id) for t in tickets],
            'status': 'accepted'})
        M.MonQTask.run_ready()
        emails = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).all()
        assert len(emails) == 1  # only admin email sent
        for email in emails:
            assert email.kwargs.subject == '[test:bugs] Mass edit changes by Test Admin'
        admin = M.User.by_username('test-admin')
        admin_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(admin._id)
        }).all()
        monitoring_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': 'monitoring@email.com'
        }).all()
        assert len(admin_email) == 1
        assert len(monitoring_email) == 0

    def test_filtered_by_subscription(self):
        self.new_ticket(summary='test first ticket', status='open')
        self.new_ticket(summary='test second ticket', status='open')
        self.new_ticket(summary='test third ticket', status='open')
        tickets = []
        users = []
        tickets.append(tm.Ticket.query.get(summary='test first ticket'))
        tickets.append(tm.Ticket.query.get(summary='test second ticket'))
        tickets.append(tm.Ticket.query.get(summary='test third ticket'))
        users.append(M.User.by_username('test-user-0'))
        users.append(M.User.by_username('test-user-1'))
        users.append(M.User.by_username('test-user-2'))
        admin = M.User.by_username('test-admin')
        tickets[0].subscribe(user=users[0])
        tickets[0].subscribe(user=users[1])
        tickets[1].subscribe(user=users[1])
        tickets[2].subscribe(user=users[2])
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()

        # Pretend we're changing first and second ticket.
        # Then we should notify test-user-0, test-user-1 and admin.
        # test-user-2 shoudn't be notified
        # (he has subscription to third ticket, but it didn't change).
        # test-user-0 should see changes only for first ticket.
        # test-user-1 - for both (separate subscription for both tickets).
        # admin - for both (tool subscription).
        changes = {
            tickets[0]._id: tickets[0],
            tickets[1]._id: tickets[1],
        }
        filtered_changes = c.app.globals.filtered_by_subscription(changes)
        filtered_users = [uid for uid, data in filtered_changes.items()]
        assert (sorted(filtered_users) ==
                sorted(u._id for u in users[:-1] + [admin]))
        ticket_ids = [t._id for t in tickets]
        assert filtered_changes[users[0]._id] == set(ticket_ids[0:1])
        assert filtered_changes[users[1]._id] == set(ticket_ids[:-1])
        assert filtered_changes[admin._id] == set(ticket_ids[:-1])

    def test_vote(self):
        r = self.new_ticket(summary='test vote').follow()
        assert r.html.find('div', {'id': 'vote'})

        # test vote form not visible to anon user
        r = self.app.get('/bugs/1/', extra_environ=dict(username='*anonymous'))
        assert not r.html.find('div', {'id': 'vote'})

        r = self.app.get('/bugs/1/')
        votes_up = r.html.find('span', {'class': 'votes-up'})
        votes_down = r.html.find('span', {'class': 'votes-down'})
        assert '0' in str(votes_up)
        assert '0' in str(votes_down)

        # invalid vote
        r = self.app.post('/bugs/1/vote', dict(vote='invalid'))
        expected_resp = json.dumps(dict(status='error', votes_up=0, votes_down=0, votes_percent=0))
        assert r.response.text == expected_resp

        # vote up
        r = self.app.post('/bugs/1/vote', dict(vote='u'))
        expected_resp = json.dumps(dict(status='ok', votes_up=1, votes_down=0, votes_percent=100))
        assert r.response.text == expected_resp

        # vote down by another user
        r = self.app.post('/bugs/1/vote', dict(vote='d'),
                          extra_environ=dict(username='test-user-0'))

        expected_resp = json.dumps(dict(status='ok', votes_up=1, votes_down=1, votes_percent=50))
        assert r.response.text == expected_resp

        # make sure that on the page we see the same result
        r = self.app.get('/bugs/1/')
        votes_up = r.html.find('span', {'class': 'votes-up'})
        votes_down = r.html.find('span', {'class': 'votes-down'})
        assert '1' in str(votes_up)
        assert '1' in str(votes_down)

        r = self.app.get('/bugs/')
        assert "Votes" in r
        self.app.post(
            '/admin/bugs/set_options',
            params={'EnableVoting': 'false'})
        r = self.app.get('/bugs/')
        assert "Votes" not in r

    @td.with_tool('test', 'Tickets', 'tracker',
                  post_install_hook=post_install_create_ticket_permission)
    def test_create_permission(self):
        """Test that user with `create` permission can create ticket,
        but can't edit it without `update` permission.
        """
        response = self.app.get('/p/test/tracker/',
                                extra_environ=dict(username='test-user-0'))
        assert 'Create Ticket' in response

        response = self.new_ticket(summary='test create, not update',
                                   mount_point='/tracker/',
                                   extra_environ=dict(username='test-user-0'))
        ticket_url = response.headers['Location']
        response = self.app.get(ticket_url,
                                extra_environ=dict(username='test-user-0'))
        assert not response.html.find('div', {'class': 'error'})
        assert not response.html.find('a', {'class': 'edit_ticket'})

    @td.with_tool('test', 'Tickets', 'tracker',
                  post_install_hook=post_install_update_ticket_permission)
    def test_update_permission(self):
        r = self.app.get('/p/test/tracker/',
                         extra_environ=dict(username='*anonymous'))
        assert 'Create Ticket' in r

        r = self.new_ticket(summary='test', mount_point='/tracker/',
                            extra_environ=dict(username='*anonymous'))
        ticket_url = r.headers['Location']
        r = self.app.get(ticket_url, extra_environ=dict(username='*anonymous'))
        a = r.html.find('a', {'class': 'icon edit_ticket'})
        assert a.text == '\xa0Edit'

    def test_ticket_creator_cant_edit_private_ticket_without_update_perm(self):
        p = M.Project.query.get(shortname='test')
        tracker = p.app_instance('bugs')
        # authenticated user has 'create' permission, but not 'update'
        role = M.ProjectRole.by_name('*authenticated')._id
        create_permission = M.ACE.allow(role, 'create')
        update_permission = M.ACE.allow(role, 'update')
        acl = tracker.config.acl
        acl.append(create_permission)
        if update_permission in acl:
            acl.remove(update_permission)
        # test-user creates private ticket
        env = {'username': 'test-user'}
        post_data = {
            'ticket_form.summary': 'Private ticket title',
            'ticket_form.private': 'True'
        }
        self.app.post('/bugs/save_ticket', post_data, extra_environ=env)
        # ... and can see it
        r = self.app.get('/bugs/1/', extra_environ=env)
        assert 'Private ticket title' in r
        assert '<label class="simple">Private:</label> Yes' in r, 'Ticket is not private'
        # ... and can't see 'Edit' link
        assert r.html.find('a', {'class': 'edit_ticket'}) is None, "Found 'Edit' link"
        # ... and can't actually edit it
        self.app.post('/bugs/1/update_ticket', {'summary': 'should fail'},
                      extra_environ=env, status=403)

    def test_imported_tickets_redirect(self):
        self.new_ticket(summary='Imported ticket')
        ticket = tm.Ticket.query.get(ticket_num=1)
        ticket.import_id = {'source_id': '42000'}
        ThreadLocalORMSession.flush_all()

        # expect permanent redirect to /p/test/bugs/1/
        r = self.app.get('/p/test/bugs/42000/', status=301).follow()
        assert r.request.path == '/p/test/bugs/1/', r.request.path

        # not found and has not import_id
        self.app.get('/p/test/bugs/42042/', status=404)

    def test_ticket_delete(self):
        self.new_ticket(summary='Test ticket')
        self.app.post('/bugs/1/delete')
        r = self.app.get('/bugs/')
        assert 'No open tickets found.' in r
        assert tm.Ticket.query.get(ticket_num=1).summary != 'Test ticket'
        self.app.post('/bugs/1/undelete')
        r = self.app.get('/bugs/')
        assert 'No open tickets found.' not in r
        assert tm.Ticket.query.get(ticket_num=1).summary == 'Test ticket'

    def test_ticket_delete_without_permission(self):
        self.new_ticket(summary='Test ticket')
        self.app.post('/bugs/1/delete',
                      extra_environ=dict(username='*anonymous'))
        r = self.app.get('/bugs/')
        assert '<a href="/p/test/bugs/1/">Test ticket</a>' in r
        self.app.post('/bugs/1/delete')
        self.app.post('/bugs/1/undelete',
                      extra_environ=dict(username='*anonymous'))
        r = self.app.get('/bugs/')
        assert 'No open tickets found.' in r

    def test_deleted_ticket_visible(self):
        self.new_ticket(summary='test')
        self.app.post('/bugs/1/delete')
        r = self.app.get('/p/test/bugs/1/')
        assert '#1 test' in r
        self.app.get('/p/test/bugs/1/',
                     extra_environ=dict(username='*anonymous'), status=404)
        r = self.app.get('/p/test/bugs/',
                         params=dict(q='test', deleted='True'))
        assert '<td><a href="/p/test/bugs/1/">test' in r
        assert '<tr class=" deleted">' in r
        r = self.app.get(
            '/p/test/bugs/', params=dict(q='test', deleted='True'),
            extra_environ=dict(username='*anonymous'))
        assert 'No open tickets found.' in r

    def test_show_hide_deleted_tickets(self):
        self.new_ticket(summary='Test ticket')
        r = self.app.get('/p/test/bugs/')
        assert 'Show deleted tickets' not in r
        self.app.post('/bugs/1/delete')
        r = self.app.get('/p/test/bugs/')
        assert 'Show deleted tickets' in r
        assert 'No open tickets found' in r
        r = self.app.get('/bugs/?deleted=True')
        assert '<a href="/p/test/bugs/1/">Test ticket' in r
        assert 'Hide deleted tickets' in r

    @td.with_tool('test', 'Tickets', 'bugs2')
    @td.with_tool('test2', 'Tickets', 'bugs')
    @td.with_tool('test2', 'Tickets', 'bugs2')
    def test_move_ticket(self):
        self.new_ticket(summary='test')
        r = self.app.get('/p/test/bugs/1/move')
        trackers = r.html.find('select', {'name': 'tracker'}).findAll('option')
        trackers = {t.text for t in trackers}
        expected = {'test/bugs', 'test/bugs2', 'test2/bugs', 'test2/bugs2'}
        assert trackers == expected, trackers

        p = M.Project.query.get(shortname='test2')
        tracker = p.app_instance('bugs2')
        r = self.app.post('/p/test/bugs/1/move/',
                          params={'tracker': str(tracker.config._id)}).follow()
        assert r.request.path == '/p/test2/bugs2/1/'
        summary = r.html.findAll('h2', {'class': 'dark title'})[0].find('span').contents[0].strip()
        assert summary == '#1 test'
        ac_id = tracker.config._id
        ticket = tm.Ticket.query.find({
            'app_config_id': ac_id,
            'ticket_num': 1}).first()
        assert ticket is not None, "Can't find moved ticket"
        assert ticket.discussion_thread.app_config_id == ac_id
        assert ticket.discussion_thread.discussion.app_config_id == ac_id
        post = ticket.discussion_thread.last_post
        assert post.text == 'Ticket moved from /p/test/bugs/1/'

    @td.with_tool('test2', 'Tickets', 'bugs2')
    def test_move_ticket_feed(self):
        self.new_ticket(summary='test')
        p = M.Project.query.get(shortname='test2')
        ac_id = p.app_instance('bugs2').config._id
        r = self.app.post('/p/test/bugs/1/move/',
                          params={'tracker': str(ac_id)}).follow()

        ticket = tm.Ticket.query.find({
            'app_config_id': ac_id,
            'ticket_num': 1}).first()
        post = ticket.discussion_thread.last_post
        ticket_link = '/p/test2/bugs2/1/?limit=25#' + post.slug
        msg = 'Ticket moved from /p/test/bugs/1/'
        assert post.text == msg
        # auto comment content and link to it should be in a ticket's feed
        r = self.app.get('/p/test2/bugs2/1/feed')
        assert msg in r, r
        assert ticket_link in r, r
        # auto comment content and link to it should be in a tracker's feed
        r = self.app.get('/p/test2/bugs2/1/feed')
        assert msg in r, r
        assert ticket_link in r, r

        # post comment and make sure that it appears on the feeds
        r = self.app.get('/p/test2/bugs2/1/')
        for f in r.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        post_content = 'ticket discussion post content'
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = post_content
        r = self.app.post(f['action'], params=params,
                          headers={'Referer': b'/p/test2/bugs2/1/'})
        r = self.app.get('/p/test2/bugs2/1/', dict(page='1'))
        assert post_content in r
        comments_cnt = len(r.html.findAll(attrs={'class': 'discussion-post'}))
        assert comments_cnt == 2  # moved auto comment + new comment
        post = ticket.discussion_thread.last_post
        # content and link to the ticket should be in a tracker's feed
        ticket_link = '/p/test2/bugs2/1/?limit=25#' + post.slug
        r = self.app.get('/p/test2/bugs2/feed')
        assert post_content in r, r
        assert ticket_link in r, r
        # content and link to the ticket should be in a ticket's feed
        r = self.app.get('/p/test2/bugs2/1/feed')
        assert post_content in r, r
        assert ticket_link in r, r

    def test_move_ticket_bad_data(self):
        self.new_ticket(summary='test')
        r = self.app.post('/p/test/bugs/1/move', extra_environ={'HTTP_REFERER': '/p/test/bugs/1/'}).follow()  # empty POST
        assert 'Select valid tracker' in r, r
        r = self.app.post('/p/test/bugs/1/move',
                          params={'tracker': 'invalid tracker id'},
                          extra_environ={'HTTP_REFERER': '/p/test/bugs/1/'}).follow()
        assert 'Select valid tracker' in r, r
        p = M.Project.query.get(shortname='test')
        tracker = p.app_instance('bugs')
        r = self.app.post('/p/test/bugs/1/move',
                          params={'tracker': str(tracker.config._id)},
                          extra_environ={'HTTP_REFERER': '/p/test/bugs/1/'}).follow()
        assert 'Ticket already in a selected tracker' in r, r

    def test_move_ticket_access(self):
        self.new_ticket(summary='test')
        self.app.get('/p/test/bugs/1/move',
                     extra_environ={'username': 'test-user'},
                     status=403)
        self.app.post('/p/test/bugs/1/move',
                      extra_environ={'username': 'test-user'},
                      status=403)

    @td.with_tool('test', 'Tickets', 'dummy')
    def test_move_ticket_redirect(self):
        self.new_ticket(summary='test 1')
        self.app.get('/p/test/bugs/1/', status=200)  # shouldn't fail

        # move ticket 1 to 'dummy' tracker
        p = M.Project.query.get(shortname='test')
        dummy_tracker = p.app_instance('dummy')
        r = self.app.post('/p/test/bugs/1/move',
                          params={'tracker': str(dummy_tracker.config._id)}).follow()
        assert r.request.path == '/p/test/dummy/1/'

        # test that old url redirects to moved ticket
        self.app.get('/p/test/bugs/1/', status=301).follow()
        assert r.request.path == '/p/test/dummy/1/'

    @td.with_tool('test', 'Tickets', 'dummy')
    def test_move_ticket_and_delete_tool(self):
        """See [#5708] for details."""
        # create two tickets and ensure they are viewable
        self.new_ticket(summary='test 1')
        self.new_ticket(summary='test 2')
        self.app.get('/p/test/bugs/1/', status=200)  # shouldn't fail
        self.app.get('/p/test/bugs/2/', status=200)  # shouldn't fail

        # move ticket 1 to 'dummy' tracker
        p = M.Project.query.get(shortname='test')
        dummy_tracker = p.app_instance('dummy')
        r = self.app.post('/p/test/bugs/1/move',
                          params={'tracker': str(dummy_tracker.config._id)}).follow()
        assert r.request.path == '/p/test/dummy/1/'

        # delete 'dummy' tracker
        p.uninstall_app('dummy')

        # remaining tickets in 'bugs' tracker should still be viewable
        self.app.get('/p/test/bugs/2/', status=200)  # shouldn't fail
        # ticket counts as moved
        r = self.app.get('/p/test/bugs/1/', status=301)
        r.follow(status=301)  # and found 'cause we don't want it to hard 404, but use default logic

    @td.with_tool('test', 'Tickets', 'dummy')
    def test_move_ticket_email_notifications(self):
        """See [#5691] for details"""
        # create two tickets and ensure they are viewable
        self.new_ticket(summary='test 1')
        self.new_ticket(summary='test 2')
        self.app.get('/p/test/bugs/1/', status=200)  # shouldn't fail
        self.app.get('/p/test/bugs/2/', status=200)  # shouldn't fail

        # move ticket 1 to 'dummy' tracker
        p = M.Project.query.get(shortname='test')
        dummy_tracker = p.app_instance('dummy')
        r = self.app.post('/p/test/bugs/1/move',
                          params={'tracker': str(dummy_tracker.config._id)}).follow()
        assert r.request.path == '/p/test/dummy/1/'

        # comment ticket 2
        M.Notification.query.remove()
        r = self.app.get('/p/test/bugs/2/')
        field_name = None  # comment text textarea name
        form = r.forms['ticket-form']
        for name, field in form.fields.items():
            if field[0].tag == 'textarea':
                field_name = name
        assert field_name, "Can't find comment field"
        form.fields[field_name][0].value = 'Hi there'
        form.submit()

        # notification for ticket 2 should reference [test:bugs], not
        # [test:dummy]
        n = M.Notification.query.find().all()[0]
        assert '[test:bugs]' in n.subject
        assert '[test:bugs]' in n.reply_to_address

    @td.with_tool('test2', 'Tickets', 'features')
    def test_move_ticket_subscriptions(self):
        """Subscriptions should move along with the ticket"""
        self.new_ticket(summary='test ticket')
        self.new_ticket(summary='another test ticket')
        p = M.Project.query.get(shortname='test')
        bugs = p.app_instance('bugs')
        p2 = M.Project.query.get(shortname='test2')
        features = p2.app_instance('features')
        admin = M.User.query.get(username='test-admin')
        user = M.User.query.get(username='test-user')

        # subscribe test-user to ticket #2
        self.app.post('/p/test/bugs/2/subscribe', {'subscribe': 'True'},
                      extra_environ={'username': 'test-user'})
        assert M.Mailbox.query.get(user_id=user._id,
                                   project_id=p._id,
                                   app_config_id=bugs.config._id,
                                   artifact_title='Ticket #2: another test ticket',
                                   artifact_url='/p/test/bugs/2/')

        # remove test-admin's tool-wide subscription to test2/features so he can get a new individual one
        M.Mailbox.query.remove({'user_id': admin._id,
                                'project_id': p2._id,
                                'app_config_id': features.config._id,
                                'artifact_index_id': None,
                                })

        # move ticket to new project & tool: test/bugs/2 => test2/features/1
        r = self.app.post('/p/test/bugs/2/move',
                          params={'tracker': str(features.config._id)}).follow()
        assert r.request.path == '/p/test2/features/1/'

        # test-user should be subscribed to it
        assert M.Mailbox.query.get(user_id=user._id,
                                   project_id=p2._id,
                                   app_config_id=features.config._id,
                                   artifact_title='Ticket #1: another test ticket',
                                   artifact_url='/p/test2/features/1/'),\
            "Could not find moved subscription.  User's record is %s" % M.Mailbox.query.get(user_id=user._id)
        # test-admin (who had a tool-level subscription) should be too
        assert M.Mailbox.query.get(user_id=admin._id,
                                   project_id=p2._id,
                                   app_config_id=features.config._id,
                                   artifact_title='Ticket #1: another test ticket',
                                   artifact_url='/p/test2/features/1/'),\
            "Could not find moved subscription.  Admin's record is %s" % M.Mailbox.query.get(user_id=admin._id)

    @td.with_tool('test2', 'Tickets', 'bugs2')
    def test_move_attachment(self):
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(
            allura.__path__[0], 'nf', 'allura', 'images', file_name)
        file_data = open(file_path, 'rb').read()
        upload = ('attachment', file_name, file_data)
        self.new_ticket(summary='test move attachment')

        # attach an image to the ticket
        self.app.post('/bugs/1/update_ticket',
                      {'summary': 'test'},
                      upload_files=[upload])
        # attach a txt file to the comment
        r = self.app.get('/p/test/bugs/1/')
        post_link = str(r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])
        r = self.app.post(post_link + 'attach',
                          upload_files=[('file_info', 'test.txt', b'test')])
        # move ticket
        p = M.Project.query.get(shortname='test2')
        bugs2 = p.app_instance('bugs2')
        r = self.app.post('/p/test/bugs/1/move/',
                          params={'tracker': str(bugs2.config._id)}).follow()

        attach_tickets = r.html.findAll('div', attrs={'class': 'attachment_thumb'})
        attach_comments = r.html.findAll('div', attrs={'class': 'attachment_item'})
        ta = str(attach_tickets)  # ticket's attachments
        ca = str(attach_comments)  # comment's attachments
        assert '<a href="/p/test2/bugs2/1/attachment/neo-icon-set-454545-256x350.png"' in ta
        assert '<img alt="Thumbnail" src="/p/test2/bugs2/1/attachment/neo-icon-set-454545-256x350.png/thumb"' in ta
        p = M.Post.query.find().sort('timestamp', 1).first()
        assert (
            '<a href="/p/test2/bugs2/_discuss/thread/%s/%s/attachment/test.txt"' %
            (p.thread_id, p.slug) in ca)
        for attach in M.BaseAttachment.query.find():
            assert attach.app_config_id == bugs2.config._id
            if attach.attachment_type == 'DiscussionAttachment':
                assert attach.discussion_id == bugs2.config.discussion_id

    @td.with_tool('test', 'Tickets', 'dummy')
    def test_move_ticket_comments(self):
        """Comments should move along with the ticket"""
        self.new_ticket(summary='test ticket')
        r = self.app.get('/p/test/bugs/1/')
        field_name = None  # comment text textarea name
        form = r.forms['ticket-form']
        for name, field in form.fields.items():
            if field[0].tag == 'textarea':
                field_name = name
        assert field_name, "Can't find comment field"
        form.fields[field_name][0].value = 'I am comment'
        form.submit()
        r = self.app.get('/p/test/bugs/1/')
        assert 'I am comment' in r

        p = M.Project.query.get(shortname='test')
        dummy_tracker = p.app_instance('dummy')
        r = self.app.post('/p/test/bugs/1/move',
                          params={'tracker': str(dummy_tracker.config._id)}).follow()
        assert r.request.path == '/p/test/dummy/1/'
        assert 'I am comment' in r

    def test_tags(self):
        p = M.Project.query.get(shortname='test')
        p.app_instance('bugs')
        self.new_ticket(summary='a', labels='tag1,tag2')
        self.new_ticket(summary='b', labels='tag2')
        self.new_ticket(summary='c', labels='42cc,test')
        # Testing only empty 'term', because mim doesn't support aggregation
        # calls
        r = self.app.get('/p/test/bugs/tags')
        assert json.loads(r.text) == []
        r = self.app.get('/p/test/bugs/tags?term=')
        assert json.loads(r.text) == []

    def test_rest_tickets(self):
        ticket_view = self.new_ticket(summary='test').follow()
        for f in ticket_view.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_attr('name'):
                params[field['name']] = field.get('value') or ''
        params[f.find('textarea')['name']] = 'test comment'
        self.app.post(f['action'], params=params,
                      headers={'Referer': b'/bugs/1/'})
        r = self.app.get('/bugs/1/', dict(page='1'))
        post_link = str(r.html.find('div', {'class': 'edit_post_form reply'}).find('form')['action'])
        self.app.post(post_link + 'attach',
                      upload_files=[('file_info', 'test.txt', b'test attach')])
        r = self.app.get('/p/test/bugs/1/')
        discussion_url = r.html.findAll('form')[-1]['action'][:-4]
        r = self.app.get('/rest/p/test/bugs/1/')
        r = json.loads(r.text)
        assert (r['ticket']['discussion_thread_url'] ==
                'http://localhost/rest%s' % discussion_url)
        slug = r['ticket']['discussion_thread']['posts'][0]['slug']
        assert (r['ticket']['discussion_thread']['posts'][0]['attachments'][0]['url'] ==
                f'http://localhost{discussion_url}{slug}/attachment/test.txt')
        assert (r['ticket']['discussion_thread']['posts'][0]['attachments'][0]['bytes'] ==
                11)

        file_name = 'test_root.py'
        file_data = open(__file__, 'rb').read()
        upload = ('attachment', file_name, file_data)
        r = self.app.post('/bugs/1/update_ticket', {
            'summary': 'test rest attach'
        }, upload_files=[upload]).follow()
        r = self.app.get('/rest/p/test/bugs/1/')
        r = json.loads(r.text)
        assert (r['ticket']['attachments'][0]['url'] ==
                'http://localhost/p/test/bugs/1/attachment/test_root.py')

    def test_html_escaping(self):
        with mock.patch.object(mail_tasks.smtp_client, '_client') as _client:
            self.new_ticket(summary='test <h2> ticket',
                            status='open', _milestone='2.0')
            ThreadLocalORMSession.flush_all()
            M.MonQTask.run_ready()
            ThreadLocalORMSession.flush_all()
            email = M.MonQTask.query.find(
                dict(task_name='allura.tasks.mail_tasks.sendmail')).first()
            assert (email.kwargs.subject ==
                    '[test:bugs] #1 test <h2> ticket')
            text = email.kwargs.text
            assert '** [bugs:#1] test &lt;h2&gt; ticket**' in text
            mail_tasks.sendmail(
                fromaddr=str(c.user._id),
                destinations=[str(c.user._id)],
                text=text,
                reply_to=g.noreply,
                subject=email.kwargs.subject,
                message_id=h.gen_message_id())
            assert _client.sendmail.call_count == 1
            return_path, rcpts, body = _client.sendmail.call_args[0]
            body = body.split('\n')
            # check subject
            assert 'Subject: [test:bugs] #1 test <h2> ticket' in body
            # check html, need tags escaped
            assert ('<p><strong> <a class="alink" href="http://localhost/p/test/bugs/1/">[bugs:#1]</a>'
                    ' test &lt;h2&gt; ticket</strong></p>' in
                    body)
            # check plaintext (ok to have "html" tags)
            assert '** [bugs:#1] test <h2> ticket**' in body

    @patch('forgetracker.search.query_filter_choices', autospec=True)
    def test_multiselect(self, query_filter_choices):
        self.new_ticket(summary='test')
        self.new_ticket(summary='test2')
        query_filter_choices.return_value = {'status': [('open', 2)], }
        r = self.app.get('/bugs/')
        assert '<option value="open">open (2)</option>' in r
        query_filter_choices.assert_called_once_with('!status_s:closed && !status_s:wont-fix', fq=['deleted_b:False'])

    def test_rate_limit_new(self):
        self.new_ticket(summary='First ticket')
        # Set rate limit to unlimit
        with h.push_config(config, **{'forgetracker.rate_limits': '{}'}):
            r = self.app.get('/bugs/new/')
            assert r.status_int == 200
        # Set rate limit to 1 in first hour of project
        with h.push_config(config, **{'forgetracker.rate_limits': '{"3600": 1}'}):
            r = self.app.get('/bugs/new/')
            assert r.status_int == 302
            assert r.location == 'http://localhost/bugs/'
            wf = json.loads(self.webflash(r))
            assert wf['status'] == 'error'
            assert (
                wf['message'] ==
                'Ticket creation rate limit exceeded. Please try again later.')

    def test_rate_limit_save_ticket(self):
        # Set rate limit to unlimit
        with h.push_config(config, **{'forgetracker.rate_limits': '{}'}):
            summary = 'Ticket w/o limit'
            post_data = {'ticket_form.summary': summary}
            r = self.app.post('/bugs/save_ticket', post_data).follow()
            assert summary in r
            t = tm.Ticket.query.get(summary=summary)
            assert t is not None
        # Set rate limit to 1 in first hour of project
        with h.push_config(config, **{'forgetracker.rate_limits': '{"3600": 1}'}):
            summary = 'Ticket with limit'
            post_data = {'ticket_form.summary': summary}
            r = self.app.post('/bugs/save_ticket', post_data)
            assert r.status_int == 302
            assert r.location == 'http://localhost/bugs/'
            wf = json.loads(self.webflash(r))
            assert wf['status'] == 'error'
            assert (
                wf['message'] ==
                'Ticket creation rate limit exceeded. Please try again later.')
            assert summary not in r.follow()
            t = tm.Ticket.query.get(summary=summary)
            assert t is None

    def test_user_missing(self):
        # add test-user to project so it can be assigned the ticket
        testuser = M.User.by_username('test-user')
        c.project.add_user(testuser, ['Developer'])
        Credentials.get().clear()
        # make a ticket created by & assigned to test-user
        self.new_ticket(summary='foo bar', assigned_to='test-user', private=True,
                        extra_environ={'username': 'test-user'})
        # but then remove the user
        M.User.query.remove({'username': 'test-user'})

        self.app.get('/p/test/bugs/1/', status=200)

        r = self.app.post('/p/test/bugs/1/update_ticket', {
            'summary': 'new summary',
            'description': 'new description',
            'status': 'closed',
            'assigned_to': '',
            'labels': '',
            'private': 'True',
            'comment': 'closing ticket of a user that is gone'
        })
        self.app.get('/p/test/bugs/1/', status=200)

    def test_bulk_delete(self):
        self.new_ticket(summary='test first ticket')
        self.new_ticket(summary='test second ticket')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        first_ticket = tm.Ticket.query.get(summary='test first ticket')
        second_ticket = tm.Ticket.query.get(summary='test second ticket')

        M.MonQTask.query.remove()
        self.app.post('/p/test/bugs/update_tickets', {
            '__search': '',
            '__ticket_ids': (
                str(first_ticket._id),
                str(second_ticket._id)),
            'deleted': 'True'})
        M.MonQTask.run_ready()

        r = self.app.get('/bugs/')
        assert 'No open tickets found.' in r
        assert tm.Ticket.query.get(ticket_num=1).summary != 'test first ticket'
        assert tm.Ticket.query.get(ticket_num=2).summary != 'test second ticket'


class TestMilestoneAdmin(TrackerTestController):
    def _post(self, params, **kw):
        params['open_status_names'] = 'aa bb'
        params['closed_status_names'] = 'cc'
        self.app.post('/admin/bugs/set_custom_fields',
                      params=variable_encode(params), **kw)
        return self.app.get('/admin/bugs/fields')

    def _post_milestones(self, milestones):
        params = {'custom_fields': [
            dict(label=mf['label'],
                 show_in_search='on',
                 type='milestone',
                 milestones=[
                     {k: v for k, v in d.items()} for d in mf['milestones']])
            for mf in milestones]}
        return self._post(params)

    def test_create_milestone_field(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta')])
        ])
        assert 'releases' in r
        assert '1.0-beta' in r

    def test_delete_milestone_field(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta')])
        ])
        self.new_ticket(summary='test new milestone',
                        **{'custom_fields._releases': '1.0-beta'})
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.0-beta'}).count() == 1
        r = self._post_milestones([])
        assert 'Releases' not in r
        assert '1.0-beta' not in r
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.0-beta'}).count() == 0

    def test_rename_milestone_field(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta')])
        ])
        self.new_ticket(summary='test new milestone',
                        **{'custom_fields._releases': '1.0-beta'})
        r = self._post_milestones([
            dict(label='versions', milestones=[dict(name='1.0/beta')])
        ])
        assert 'Releases' not in r
        assert 'versions' in r
        assert '1.0-beta' in r
        # TODO: This doesn't work - need to make milestone custom fields
        #       renameable.
        # assert tm.Ticket.query.find({
        #    'custom_fields._versions': '1.0-beta'}).count() == 1

    def test_create_milestone(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta')])
        ])
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta'),
                                               dict(name='2.0')])
        ])
        assert '1.0-beta' in r
        assert '2.0' in r

    def test_delete_milestone(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta')])
        ])
        self.new_ticket(summary='test new milestone',
                        **{'custom_fields._releases': '1.0-beta'})
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.0-beta'}).count() == 1
        r = self._post_milestones([
            dict(label='releases', milestones=[])
        ])
        assert 'releases' in r
        assert '1.0-beta' not in r
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.0-beta'}).count() == 0

    def test_rename_milestone(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0')])
        ])
        self.new_ticket(summary='test new milestone',
                        **{'custom_fields._releases': '1.0'})
        r = self._post_milestones([
            dict(label='releases', milestones=[
                dict(name='1.1', old_name='1.0')])
        ])
        assert 'releases' in r
        assert '1.0' not in r
        assert '1.1' in r
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.0'}).count() == 0
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.1'}).count() == 1


def post_install_hook(app):
    role_anon = M.ProjectRole.by_name('*anonymous')._id
    app.config.acl.append(M.ACE.allow(role_anon, 'post'))
    app.config.acl.append(M.ACE.allow(role_anon, 'create'))
    app.config.acl.append(M.ACE.allow(role_anon, 'update'))


class TestEmailMonitoring(TrackerTestController):

    @classmethod
    def setup_class(cls):
        cls.test_email = 'mailinglist@example.com'

    def _set_options(self, monitoring_type='AllTicketChanges'):
        r = self.app.post('/admin/bugs/set_options', params={
            'TicketMonitoringEmail': self.test_email,
            'TicketMonitoringType': monitoring_type,
        })
        return r

    def test_set_options(self):
        r = self._set_options()
        r = self.app.get('/admin/bugs/options')
        email = r.html.findAll(attrs=dict(name='TicketMonitoringEmail'))
        mtype = r.html.findAll('option', attrs=dict(value='AllTicketChanges'))
        assert email[0]['value'] == self.test_email
        assert mtype[0].has_attr('selected')

    @td.with_tool('test', 'Tickets', 'doc-bugs', post_install_hook=post_install_hook)
    @patch('forgetracker.model.ticket.Notification.send_direct')
    @patch('allura.model.discuss.Thread.is_spam')
    def test_notifications_moderators(self, is_spam, send_direct):
        is_spam.return_value = False
        ticket_view = self.new_ticket(summary='test moderation', mount_point='/doc-bugs/').follow()
        _, form = find(ticket_view.forms, lambda f: f.action.endswith('/post'))
        field, _ = find(form.fields, lambda f: f[0].tag == 'textarea')
        form.set(field, 'this is an anonymous comment')
        form.submit(extra_environ=dict(username='*anonymous'))
        send_direct.assert_called_with(
            str(M.User.query.get(username='test-admin')._id))

    @td.with_tool('test', 'Tickets', 'doc-bugs', post_install_hook=post_install_hook)
    @patch('forgetracker.model.ticket.Notification.send_direct')
    @patch('allura.model.discuss.Thread.is_spam')
    def test_notifications_off_spam(self, is_spam, send_direct):
        # like test_notifications_moderators but no notification because it goes straight to spam status
        is_spam.return_value = True
        ticket_view = self.new_ticket(summary='test moderation', mount_point='/doc-bugs/').follow()
        _, form = find(ticket_view.forms, lambda f: f.action.endswith('/post'))
        field, _ = find(form.fields, lambda f: f[0].tag == 'textarea')
        form.set(field, 'this is an anonymous comment')
        form.submit(extra_environ=dict(username='*anonymous'))
        assert not send_direct.called

    @patch('forgetracker.model.ticket.Notification.send_simple')
    def test_notifications_new(self, send_simple):
        self._set_options('NewTicketsOnly')
        self.new_ticket(summary='test', private=True)
        send_simple.assert_called_once_with(self.test_email)

    @patch('forgetracker.model.ticket.Notification.send_simple')
    def test_notifications_new_public_only(self, send_simple):
        """Test that notification not sent for new private ticket
        if "public only" option selected.
        """
        self._set_options('NewPublicTicketsOnly')
        self.new_ticket(summary='test', private=True)
        assert not send_simple.called

    @patch('forgetracker.tracker_main.M.Notification.send_simple')
    def test_notifications_all(self, send_simple):
        self._set_options()
        self.new_ticket(summary='test')
        send_simple.assert_called_once_with(self.test_email)
        send_simple.reset_mock()
        response = self.app.post('/bugs/1/update_ticket', {
            'summary': 'test',
            'description': 'update',
            'private': '1'})
        assert send_simple.call_count == 1, send_simple.call_count
        send_simple.assert_called_with(self.test_email)
        send_simple.reset_mock()
        response = response.follow()
        for f in response.html.findAll('form'):
            # Dirty way to find comment form
            if (('thread' in f['action']) and ('post' in f['action'])):
                params = {i['name']: i.get('value', '')
                          for i in f.findAll('input')
                          if i.has_attr('name')}
                params[f.find('textarea')['name']] = 'foobar'
                self.app.post(str(f['action']), params)
                break  # Do it only once if many forms met
        assert send_simple.call_count == 1, send_simple.call_count
        send_simple.assert_called_with(self.test_email)

    @patch('forgetracker.tracker_main.M.Notification.send_simple')
    def test_notifications_all_public_only(self, send_simple):
        """Test that notifications are not sent for private tickets
        if "public only" option selected.
        """
        self._set_options('AllPublicTicketChanges')
        self.new_ticket(summary='test')
        send_simple.assert_called_once_with(self.test_email)
        send_simple.reset_mock()
        self.app.post('/bugs/1/update_ticket', {
            'summary': 'test',
            'description': 'update 1'})
        send_simple.assert_called_once_with(self.test_email)
        send_simple.reset_mock()
        self.app.post('/bugs/1/update_ticket', {
            'summary': 'test',
            'description': 'update 2',
            'private': '1'})
        assert not send_simple.called

    @patch('forgetracker.tracker_main.M.Notification.send_simple')
    def test_notifications_off(self, send_simple):
        """Test that tracker notification email is not sent if notifications
        are disabled at the project level.
        """
        p = M.Project.query.get(shortname='test')
        p.notifications_disabled = True
        self._set_options()
        with patch.object(M.Project.query, 'get') as get:
            get.side_effect = lambda *a, **k: None if 'bugs' in k.get('shortname', '') else p
            self.new_ticket(summary='test')
        assert send_simple.call_count == 0, send_simple.call_count

    def test_footer(self):
        self._set_options(monitoring_type='AllTicketChanges')
        M.MonQTask.query.remove()
        self.new_ticket(summary='test')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        email_tasks = M.MonQTask.query.find(
            dict(task_name='allura.tasks.mail_tasks.sendsimplemail')).all()
        assert 'Sent from localhost because mailinglist@example.com is subscribed to http://localhost/p/test/bugs/' in \
               email_tasks[0].kwargs['text']
        assert 'a project admin can change settings at http://localhost/p/test/admin/bugs/options' in \
               email_tasks[0].kwargs['text']


class TestCustomUserField(TrackerTestController):
    def setup_method(self, method):
        super().setup_method(method)
        params = dict(
            custom_fields=[
                dict(name='_code_review', label='Code Review', type='user',
                     show_in_search='on')],
            open_status_names='aa bb',
            closed_status_names='cc',
        )
        self.app.post(
            '/admin/bugs/set_custom_fields',
            params=variable_encode(params))

    def test_blank_user(self):
        kw = {'custom_fields._code_review': ''}
        ticket_view = self.new_ticket(summary='test custom fields', **kw).follow()
        # summary header shows 'nobody'
        assert (squish_spaces(ticket_view.html.findAll('label', 'simple', text='Code Review:')[0].parent.text) ==
                ' Code Review: nobody ')
        # form input is blank
        select = ticket_view.html.find('select',
                                       dict(name='ticket_form.custom_fields._code_review'))
        selected = None
        for option in select.findChildren():
            if option.has_attr('selected'):
                selected = option
        assert selected is None

    def test_project_member(self):
        kw = {'custom_fields._code_review': 'test-admin'}
        ticket_view = self.new_ticket(summary='test custom fields', **kw).follow()
        # summary header shows 'Test Admin'
        assert (squish_spaces(ticket_view.html.findAll('label', 'simple', text='Code Review:')[0].parent.text) ==
                ' Code Review: Test Admin ')
        # form input is blank
        select = ticket_view.html.find('select',
                                       dict(name='ticket_form.custom_fields._code_review'))
        selected = None
        for option in select.findChildren():
            if option.has_attr('selected'):
                selected = option
        assert selected['value'] == 'test-admin'

    def test_change_user_field(self):
        kw = {'custom_fields._code_review': ''}
        r = self.new_ticket(summary='test custom fields', **kw).follow()
        f = self._find_update_ticket_form(r)
        f['ticket_form.custom_fields._code_review'].force_value('test-admin')
        r = f.submit().follow()
        assert '<li><strong>Code Review</strong>: Test Admin' in r

    def test_search_results(self):
        kw = {'custom_fields._code_review': 'test-admin'}
        self.new_ticket(summary='test custom fields', **kw)
        r = self.app.get('/bugs/')
        assert r.html.find('table', 'ticket-list').findAll('th')[7].text.strip()[:11] == 'Code Review'
        assert r.html.find('table', 'ticket-list').tbody.tr.findAll('td')[7].text == 'Test Admin'


class TestHelpTextOptions(TrackerTestController):
    def _set_options(self, new_txt='', search_txt=''):
        r = self.app.post('/admin/bugs/set_options', params={
            'TicketHelpNew': new_txt,
            'TicketHelpSearch': search_txt,
        })
        return r

    def test_help_text(self):
        self._set_options(
            new_txt='**foo**',
            search_txt='*bar*')
        r = self.app.get('/bugs/')
        assert '<em>bar</em>' in r
        r = self.app.get('/bugs/search/', params=dict(q='test'))
        assert '<em>bar</em>' in r
        r = self.app.get('/bugs/milestone/1.0/')
        assert '<em>bar</em>' in r
        r = self.app.get('/bugs/new/')
        assert '<strong>foo</strong>' in r

        self._set_options()
        r = self.app.get('/bugs/')
        assert len(
            r.html.findAll(attrs=dict(id='search-ticket-help-msg'))) == 0
        r = self.app.get('/bugs/search/', params=dict(q='test'))
        assert len(
            r.html.findAll(attrs=dict(id='search-ticket-help-msg'))) == 0
        r = self.app.get('/bugs/milestone/1.0/')
        assert len(
            r.html.findAll(attrs=dict(id='search-ticket-help-msg'))) == 0
        r = self.app.get('/bugs/new/')
        assert len(r.html.findAll(attrs=dict(id='new-ticket-help-msg'))) == 0


class TestShowDefaultFields(TrackerTestController):

    def test_show_default_fields(self):
        r = self.app.get('/admin/bugs/fields')
        assert '<td>Ticket Number</td> <td><input type="checkbox" name="ticket_num" checked ></td>' in r
        assert '<td>Summary</td> <td><input type="checkbox" name="summary" checked ></td>' in r
        assert '<td>Milestone</td> <td><input type="checkbox" name="_milestone" checked ></td>' in r
        assert '<td>Status</td> <td><input type="checkbox" name="status" checked ></td>' in r
        assert '<td>Owner</td> <td><input type="checkbox" name="assigned_to" checked ></td>' in r
        assert '<td>Creator</td> <td><input type="checkbox" name="reported_by" ></td>' in r
        assert '<td>Created</td> <td><input type="checkbox" name="created_date" checked ></td>' in r
        assert '<td>Updated</td> <td><input type="checkbox" name="mod_date" checked ></td>' in r
        assert '<td>Labels</td> <td><input type="checkbox" name="labels" ></td>' in r
        self.new_ticket(summary='test')
        M.MonQTask.run_ready()
        r = self.app.get('/bugs/search/', params=dict(q='test'))
        assert '<td><a href="/p/test/bugs/1/">1</a></td>' in r
        p = M.Project.query.get(shortname='test')
        app = p.app_instance('bugs')
        app.globals.show_in_search['ticket_num'] = False
        r = self.app.get('/bugs/search/', params=dict(q='test'))
        assert '<td><a href="/p/test/bugs/1/">1</a></td>' not in r
        self.app.post('/admin/bugs/allow_default_field',
                      params={'status': 'on'})
        r = self.app.get('/admin/bugs/fields')
        assert '<td>Ticket Number</td> <td><input type="checkbox" name="ticket_num" ></td>' in r
        assert '<td>Summary</td> <td><input type="checkbox" name="summary" ></td>' in r
        assert '<td>Milestone</td> <td><input type="checkbox" name="_milestone" ></td>' in r
        assert '<td>Status</td> <td><input type="checkbox" name="status" checked ></td>' in r
        assert '<td>Owner</td> <td><input type="checkbox" name="assigned_to" ></td>' in r
        assert '<td>Creator</td> <td><input type="checkbox" name="reported_by" ></td>' in r
        assert '<td>Created</td> <td><input type="checkbox" name="created_date" ></td>' in r
        assert '<td>Updated</td> <td><input type="checkbox" name="mod_date" ></td>' in r
        assert '<td>Labels</td> <td><input type="checkbox" name="labels" ></td>' in r


class TestBulkMove(TrackerTestController):
    def setup_method(self, method):
        super().setup_method(method)
        self.new_ticket(summary='A New Hope')
        self.new_ticket(summary='The Empire Strikes Back')
        self.new_ticket(summary='Return Of The Jedi')
        M.MonQTask.run_ready()

    def test_access_restriction(self):
        self.app.get('/bugs/move/', status=200)
        self.app.get('/bugs/move/',
                     extra_environ={'username': 'test-user-0'},
                     status=403)
        self.app.get('/bugs/move/',
                     extra_environ={'username': '*anonymous'},
                     status=302)
        self.app.post('/bugs/move_tickets',
                      extra_environ={'username': 'test-user-0'},
                      status=403)

    def test_ticket_list(self):
        r = self.app.get('/bugs/move/?q=The')
        tickets_table = r.html.find('tbody', attrs={'class': 'ticket-list'})
        tickets = tickets_table.findAll('tr')
        assert len(tickets) == 2
        assert 'The Empire Strikes Back' in tickets_table.text
        assert 'Return Of The Jedi' in tickets_table.text

    @td.with_tool('test', 'Tickets', 'bugs2')
    @td.with_tool('test2', 'Tickets', 'bugs')
    @td.with_tool('test2', 'Tickets', 'bugs2')
    def test_controls_present(self):
        r = self.app.get('/bugs/move/')
        trackers = r.html.find('select', {'name': 'tracker'}).findAll('option')
        trackers = {t.text for t in trackers}
        expected = {'test/bugs', 'test/bugs2', 'test2/bugs', 'test2/bugs2'}
        assert trackers == expected
        move_btn = r.html.find('input', attrs={'type': 'submit', 'value': 'Move'})
        assert move_btn is not None

    @td.with_tool('test2', 'Tickets', 'bugs')
    def test_move(self):
        tickets = [
            tm.Ticket.query.find(
                {'summary': 'The Empire Strikes Back'}).first(),
            tm.Ticket.query.find({'summary': 'Return Of The Jedi'}).first()]
        p = M.Project.query.get(shortname='test2')
        original_p = M.Project.query.get(shortname='test')
        tracker = p.app_instance('bugs')
        original_tracker = original_p.app_instance('bugs')
        self.app.post('/p/test/bugs/move_tickets', {
            'tracker': str(tracker.config._id),
            '__ticket_ids': [str(t._id) for t in tickets],
            '__search': '',
        })
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        ac_id = tracker.config._id
        original_ac_id = original_tracker.config._id
        moved_tickets = tm.Ticket.query.find({'app_config_id': ac_id}).all()
        original_tickets = tm.Ticket.query.find({'app_config_id': original_ac_id}).all()
        assert len(moved_tickets) == 2
        assert len(original_tickets) == 1
        for ticket in moved_tickets:
            assert ticket.discussion_thread.app_config_id == ac_id
            assert ticket.discussion_thread.discussion.app_config_id == ac_id
            post = ticket.discussion_thread.last_post
            assert 'Ticket moved from /p/test/bugs/' in post.text
        for t in original_tickets:
            assert t.discussion_thread.app_config_id == original_ac_id
            assert t.discussion_thread.discussion.app_config_id == original_ac_id
            assert t.discussion_thread.last_post is None

    @td.with_tool('test2', 'Tickets', 'bugs2')
    def test_notifications(self):
        tickets = [
            tm.Ticket.query.find({'summary': 'A New Hope'}).first(),
            tm.Ticket.query.find(
                {'summary': 'The Empire Strikes Back'}).first(),
            tm.Ticket.query.find({'summary': 'Return Of The Jedi'}).first()]
        p = M.Project.query.get(shortname='test2')
        tracker = p.app_instance('bugs2')
        first_user = M.User.by_username('test-user-0')
        second_user = M.User.by_username('test-user-1')
        admin = M.User.by_username('test-admin')
        tickets[0].subscribe(user=first_user)
        tickets[1].subscribe(user=second_user)
        M.MonQTask.query.remove()
        self.app.post('/p/test/bugs/move_tickets', {
            'tracker': str(tracker.config._id),
            '__ticket_ids': [str(t._id) for t in tickets],
            '__search': '',
        })
        M.MonQTask.run_ready()
        emails = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).all()
        assert len(emails) == 3
        for email in emails:
            assert (email.kwargs.subject ==
                    '[test:bugs] Mass ticket moving by Test Admin')
        first_user_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(first_user._id)
        }).all()
        assert len(first_user_email) == 1
        first_user_email = first_user_email[0]
        second_user_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(second_user._id)
        }).all()
        assert len(second_user_email) == 1
        second_user_email = second_user_email[0]
        admin_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(admin._id)
        }).all()
        assert len(admin_email) == 1
        admin_email = admin_email[0]

        email_header = 'Tickets were moved from [test:bugs] to [test2:bugs2]\n'
        first_ticket_changes = 'A New Hope'
        second_ticket_changes = 'The Empire Strikes Back'
        third_ticket_changes = 'Return Of The Jedi'
        assert email_header in first_user_email.kwargs.text
        assert first_ticket_changes in first_user_email.kwargs.text
        assert email_header in second_user_email.kwargs.text
        assert second_ticket_changes in second_user_email.kwargs.text
        assert email_header in admin_email.kwargs.text
        assert first_ticket_changes in admin_email.kwargs.text
        assert second_ticket_changes in admin_email.kwargs.text
        assert third_ticket_changes in admin_email.kwargs.text
        # After tickets moved, user should see a flash
        mbox = M.Mailbox.query.get(user_id=admin._id, is_flash=True)
        notification_id = mbox.queue[-1]
        notification = M.Notification.query.get(_id=notification_id)
        assert (notification.text ==
                'Tickets moved from test/bugs to test2/bugs2')

    @td.with_tool('test2', 'Tickets', 'bugs2')
    def test_monitoring_email(self):
        self.app.post('/admin/bugs/set_options', params={
            'TicketMonitoringEmail': 'monitoring@email.com',
            'TicketMonitoringType': 'AllTicketChanges',
        })
        tickets = [
            tm.Ticket.query.find({'summary': 'A New Hope'}).first(),
            tm.Ticket.query.find(
                {'summary': 'The Empire Strikes Back'}).first(),
            tm.Ticket.query.find({'summary': 'Return Of The Jedi'}).first()]
        p = M.Project.query.get(shortname='test2')
        tracker = p.app_instance('bugs2')
        M.MonQTask.query.remove()
        self.app.post('/p/test/bugs/move_tickets', {
            'tracker': str(tracker.config._id),
            '__ticket_ids': [str(t._id) for t in tickets],
            '__search': '',
        })
        M.MonQTask.run_ready()
        emails = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).all()
        assert len(emails) == 2
        for email in emails:
            assert (email.kwargs.subject ==
                    '[test:bugs] Mass ticket moving by Test Admin')
        admin_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(M.User.by_username('test-admin')._id)
        }).all()
        monitoring_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': 'monitoring@email.com'
        }).all()
        assert len(admin_email) == 1
        assert len(monitoring_email) == 1
        admin_email_text = admin_email[0].kwargs.text
        assert ('test:bugs:#1 --> test2:bugs2:#1 A New Hope' in
                admin_email_text)
        assert ('test:bugs:#2 --> test2:bugs2:#2 The Empire Strikes Back' in
                admin_email_text)
        assert ('test:bugs:#3 --> test2:bugs2:#3 Return Of The Jedi' in
                admin_email_text)
        monitoring_email_text = monitoring_email[0].kwargs.text
        assert ('test:bugs:#1 --> test2:bugs2:#1 A New Hope' in
                monitoring_email_text)
        assert ('test:bugs:#2 --> test2:bugs2:#2 The Empire Strikes Back' in
                monitoring_email_text)
        assert ('test:bugs:#3 --> test2:bugs2:#3 Return Of The Jedi' in
                monitoring_email_text)

    @td.with_tool('test2', 'Tickets', 'bugs2')
    def test_monitoring_email_public_only(self):
        """Test that private tickets are not included in bulk move
        notifications if the "public only" option is selected.
        """
        self.app.post('/admin/bugs/set_options', params={
            'TicketMonitoringEmail': 'monitoring@email.com',
            'TicketMonitoringType': 'AllPublicTicketChanges',
        })
        self.new_ticket(summary='test first ticket', status='open')
        self.new_ticket(summary='test second ticket', status='open', private=True)
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        tickets = [
            tm.Ticket.query.find({'summary': 'test first ticket'}).first(),
            tm.Ticket.query.find({'summary': 'test second ticket'}).first()]
        M.MonQTask.query.remove()
        p = M.Project.query.get(shortname='test2')
        tracker = p.app_instance('bugs2')
        self.app.post('/p/test/bugs/move_tickets', {
            'tracker': str(tracker.config._id),
            '__ticket_ids': [str(t._id) for t in tickets],
            '__search': '',
        })
        M.MonQTask.run_ready()
        emails = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).all()
        # one for admin and one for monitoring email
        assert len(emails) == 2
        for email in emails:
            assert (email.kwargs.subject ==
                    '[test:bugs] Mass ticket moving by Test Admin')
        admin = M.User.by_username('test-admin')
        admin_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(admin._id)
        }).all()
        monitoring_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': 'monitoring@email.com'
        }).all()
        assert len(admin_email) == 1
        assert len(monitoring_email) == 1
        admin_email_text = admin_email[0].kwargs.text
        monitoring_email_text = monitoring_email[0].kwargs.text
        assert 'second ticket' in admin_email_text
        assert 'second ticket' not in monitoring_email_text

    @td.with_tool('test2', 'Tickets', 'bugs2')
    def test_monitoring_email_all_private_moved(self):
        """Test that no monitoring email is sent if the "public only"
        option is selected, and only private tickets were moved.
        """
        self.app.post('/admin/bugs/set_options', params={
            'TicketMonitoringEmail': 'monitoring@email.com',
            'TicketMonitoringType': 'AllPublicTicketChanges',
        })
        self.new_ticket(summary='test first ticket', status='open', private=True)
        self.new_ticket(summary='test second ticket', status='open', private=True)
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        tickets = [
            tm.Ticket.query.find({'summary': 'test first ticket'}).first(),
            tm.Ticket.query.find({'summary': 'test second ticket'}).first()]
        M.MonQTask.query.remove()
        p = M.Project.query.get(shortname='test2')
        tracker = p.app_instance('bugs2')
        self.app.post('/p/test/bugs/move_tickets', {
            'tracker': str(tracker.config._id),
            '__ticket_ids': [str(t._id) for t in tickets],
            '__search': '',
        })
        M.MonQTask.run_ready()
        emails = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).all()
        assert len(emails) == 1  # only admin email sent
        for email in emails:
            assert (email.kwargs.subject ==
                    '[test:bugs] Mass ticket moving by Test Admin')
        admin = M.User.by_username('test-admin')
        admin_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': str(admin._id)
        }).all()
        monitoring_email = M.MonQTask.query.find({
            'task_name': 'allura.tasks.mail_tasks.sendmail',
            'kwargs.destinations': 'monitoring@email.com'
        }).all()
        assert len(admin_email) == 1
        assert len(monitoring_email) == 0


def sidebar_contains(response, text):
    sidebar_menu = response.html.find('div', attrs={'id': 'sidebar'})
    return text in str(sidebar_menu)


class TestStats(TrackerTestController):
    def test_stats(self):
        r = self.app.get('/bugs/stats/', status=200)
        assert '# tickets: 0' in r.text


class TestNotificationEmailGrouping(TrackerTestController):
    def test_new_ticket_message_id(self):
        self.new_ticket(summary='Test Ticket')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        email = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).first()
        ticket = tm.Ticket.query.get(ticket_num=1)
        assert email.kwargs.message_id == ticket.message_id()
        assert email.kwargs.in_reply_to is None
        assert email.kwargs.references == []

    def test_comments(self):
        ticket_view = self.new_ticket(summary='Test Ticket').follow()
        ThreadLocalORMSession.flush_all()
        M.MonQTask.query.remove()
        ThreadLocalORMSession.flush_all()
        _, form = find(ticket_view.forms, lambda f: f.action.endswith('/post'))
        field, _ = find(form.fields, lambda f: f[0].tag == 'textarea')
        form.set(field, 'top-level comment')
        r = form.submit()
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        # Check that comment notification refers ticket's message id
        email = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).first()
        ticket = tm.Ticket.query.get(ticket_num=1)
        top_level_comment = ticket.discussion_thread.posts[0]
        top_level_comment_msg_id = ticket.url() + top_level_comment._id
        assert email.kwargs.message_id == top_level_comment_msg_id
        assert email.kwargs.in_reply_to == ticket.message_id()
        assert email.kwargs.references == [ticket.message_id()]

        ThreadLocalORMSession.flush_all()
        M.MonQTask.query.remove()
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/bugs/1/')
        _, form = find(r.forms, lambda f: f.action.endswith('/reply'))
        field, _ = find(form.fields, lambda f: f[0].tag == 'textarea')
        reply_text = 'Reply to top-level-comment'
        form.set(field, reply_text)
        r = form.submit()
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        # Check that reply notification refers top-level comment's message id
        email = M.MonQTask.query.find(dict(task_name='allura.tasks.mail_tasks.sendmail')).first()
        ticket = tm.Ticket.query.get(ticket_num=1)
        reply = [post for post in ticket.discussion_thread.posts if post.text == reply_text][0]
        assert email.kwargs.message_id == ticket.url() + reply._id
        assert email.kwargs.in_reply_to == top_level_comment_msg_id
        assert (email.kwargs.references ==
                [ticket.message_id(), top_level_comment_msg_id])


def test_status_passthru():
    setup_basic_test()
    c.project = M.Project.query.get(shortname='test')
    c.user = M.User.by_username('test-admin')
    c.project.install_app('tickets', mount_point='tsp',
                          open_status_names='foo bar', closed_status_names='qux baz')
    ThreadLocalORMSession.flush_all()
    app = c.project.app_instance('tsp')
    assert app.globals.set_of_open_status_names == {'foo', 'bar'}
    assert app.globals.set_of_closed_status_names == {'qux', 'baz'}
    assert 'open_status_names' not in app.config.options
    assert 'closed_status_names' not in app.config.options


class TestArtifactLinks(TrackerTestController):
    @td.with_tool('test', 'Tickets', 'features')
    def test_ambiguous_shortlinks(self):
        # Problem:
        # Two 'ticket' tools in one projects. Both have ticket #1.
        # When creating a link from within one of the tools to ticket #1 (e.g. [#1])
        # you may end up linking to another tool's ticket #1.
        # It depends on what shortlink was encountered first.
        # This test ensures this does not happening.

        project = M.Project.query.get(shortname='test')
        bugs = project.app_instance('bugs')
        features = project.app_instance('features')
        self.new_ticket('/bugs/', summary='Ticket 1 in bugs', _milestone='1.0').follow()
        self.new_ticket('/features/', summary='Ticket 1 in features', _milestone='1.0').follow()
        ticket_bugs = tm.Ticket.query.get(summary='Ticket 1 in bugs')
        ticket_features = tm.Ticket.query.get(summary='Ticket 1 in features')
        assert ticket_bugs.ticket_num == 1
        assert ticket_bugs.app.config._id == bugs.config._id
        assert ticket_features.ticket_num == 1
        assert ticket_features.app.config._id == features.config._id

        c.app = bugs
        link = '<div class="markdown_content"><p><a class="alink" href="/p/test/bugs/1/">[#1]</a></p></div>'
        assert g.markdown.convert('[#1]') == link

        c.app = features
        link = '<div class="markdown_content"><p><a class="alink" href="/p/test/features/1/">[#1]</a></p></div>'
        assert g.markdown.convert('[#1]') == link
