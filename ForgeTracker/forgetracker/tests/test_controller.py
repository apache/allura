from urllib import urlencode

from mock import Mock, patch
from tg import config
from nose.tools import assert_true
from ming.orm.base import session

from pyforge.lib import helpers as h
from pyforge.model import User
from pylons import c
from forgetracker.tests import TestController
from forgetracker.model import Ticket, Globals
from forgetracker import tracker_main


class WithUserAndBugsApp(TestController):
    def setUp(self):
        super(WithUserAndBugsApp, self).setUp()
        c.user = User.query.get(username='test_user')
        h.set_context('test', 'bugs')


class TestRootController(TestController):
    def test_index(self):
        response = self.app.get('/tickets/')
        assert_true('ForgeTracker for' in response)


class TestWhenSearchingWithCustomFields(WithUserAndBugsApp):
    def test_that_fields_are_in_search_results(self):
        response = self._search_results()
        assert response.html.find(
            lambda tag: (tag.name == 'td'
                         and 'Iteration 1' in str(tag)))

    def test_that_field_names_are_in_table_head(self):
        response = self._search_results()
        assert response.html.find(
            lambda tag: (tag.name == 'th'
                         and 'Iteration Number' in str(tag)))

    def _search_results(self):
        with search_returning_colors_are_wrong_ticket():
            response = self.app.get('/bugs/search/?q=friends')
        return response


class TestWhenLoadingFrontPage(WithUserAndBugsApp):
    def test_that_recent_tickets_are_shown(self):
        with search_returning_colors_are_wrong_ticket():
            response = tracker_main.RootController().index()
        tickets = response['tickets']
        assert tickets[0].summary == 'colors are wrong'


def search_returning_colors_are_wrong_ticket():
    ticket = create_colors_are_wrong_ticket()
    search_artifact = Mock()
    matches = Mock()
    matches.docs = [dict(ticket_num_i=ticket.ticket_num)]
    search_artifact.return_value = matches
    return patch('forgetracker.tracker_main.search_artifact', search_artifact)


def create_colors_are_wrong_ticket():
    set_tracker_custom_fields([dict(name='iteration_number',
                                    label='Iteration Number')])
    ticket = create_ticket(summary="colors are wrong",
                           custom_fields=dict(iteration_number='Iteration 1'))
    ticket.commit()
    session(ticket).flush()
    return ticket


def set_tracker_custom_fields(custom_fields):
    tracker_globals = Globals.for_current_tracker()
    tracker_globals.custom_fields = custom_fields
    session(tracker_globals).flush()


def create_ticket(summary, custom_fields):
    ticket = Ticket(app_config_id=c.app.config._id,
                    ticket_num=1,
                    summary=summary,
                    custom_fields=custom_fields)
    session(ticket).flush()
    return ticket

