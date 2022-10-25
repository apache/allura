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

import unittest

from mock import Mock, patch
from ming.orm.ormsession import session
from tg import tmpl_context as c

from allura.lib import helpers as h
from allura.model import User

from forgetracker.tests.unit import TrackerTestWithModel
from forgetracker.model import Ticket
from forgetracker import tracker_main


class WithUserAndBugsApp(TrackerTestWithModel):

    def setup_method(self, method):
        super().setup_method(method)
        c.user = User(username='test-user')
        h.set_context('test', 'bugs', neighborhood='Projects')


class TestWhenSearchingWithCustomFields(WithUserAndBugsApp):

    def setup_method(self, method):
        super().setup_method(method)
        with solr_search_returning_colors_are_wrong_ticket():
            self.response = tracker_main.RootController().search(q='friends')

    def test_that_sortable_custom_fields_are_present(self):
        expected = [dict(sortable_name='_iteration_number_s',
                         name='_iteration_number',
                         label='Iteration Number')]
        assert self.response['sortable_custom_fields'] == expected

    def test_that_tickets_are_listed(self):
        assert self.response['tickets'][0].summary == 'colors are wrong'


class TestWhenLoadingFrontPage(WithUserAndBugsApp):

    def setup_method(self, method):
        super().setup_method(method)
        with mongo_search_returning_colors_are_wrong_ticket():
            self.response = tracker_main.RootController().index()

    def test_that_recent_tickets_are_shown(self):
        tickets = self.response['tickets']
        assert tickets[0].summary == 'colors are wrong'


def solr_search_returning_colors_are_wrong_ticket():
    ticket = create_colors_are_wrong_ticket()
    search_artifact = Mock()
    matches = Mock()
    matches.docs = [dict(id=ticket.index_id())]
    matches.facets = {'facet_fields': {}}
    search_artifact.return_value = matches
    return patch('forgetracker.model.ticket.search_artifact', search_artifact)


def mongo_search_returning_colors_are_wrong_ticket():
    ticket = create_colors_are_wrong_ticket()
    tickets = [ticket]
    paged_query = Mock()
    paged_query.return_value = dict(tickets=tickets)
    return patch('forgetracker.tracker_main.TM.Ticket.paged_query', paged_query)


def create_colors_are_wrong_ticket():
    set_tracker_custom_fields([dict(name='_iteration_number',
                                    label='Iteration Number',
                                    type='number',
                                    show_in_search=True)])
    ticket = create_ticket(summary="colors are wrong",
                           custom_fields=dict(_iteration_number='Iteration 1'))
    ticket.commit()
    session(ticket).flush()
    return ticket


def set_tracker_custom_fields(custom_fields):
    c.app.globals.custom_fields = custom_fields
    session(c.app.globals).flush()


def create_ticket(summary, custom_fields):
    ticket = Ticket(app_config_id=c.app.config._id,
                    ticket_num=1,
                    summary=summary,
                    custom_fields=custom_fields)
    session(ticket).flush()
    return ticket


class test_change_text(unittest.TestCase):

    def test_get_label(self):
        self.assertEqual('Milestone', tracker_main.get_label('_milestone'))
        self.assertEqual('Ticket Number', tracker_main.get_label('ticket_num'))
        self.assertEqual('Summary', tracker_main.get_label('summary'))
        self.assertEqual('Status', tracker_main.get_label('status'))
        self.assertEqual('Owner', tracker_main.get_label('assigned_to'))
        self.assertEqual(None, tracker_main.get_label('test'))

    def test_get_change_text(self):
        self.assertEqual(
            '- **test**: value2 --> value1\n',
            tracker_main.get_change_text('test', 'value1', 'value2'))

    def test_get_change_text_for_lists(self):
        self.assertEqual(
            '- **test**: v1, v2 --> v3, v4, v5\n',
            tracker_main.get_change_text('test', ['v3', 'v4', 'v5'], ['v1', 'v2']))
