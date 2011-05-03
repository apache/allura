from mock import Mock, patch
from ming.orm.ormsession import session

from allura.lib import helpers as h
from allura.model import User
from pylons import c
from forgetracker.tests.unit import TrackerTestWithModel
from forgetracker.model import Ticket, Globals
from forgetracker import tracker_main


class WithUserAndBugsApp(TrackerTestWithModel):
    def setUp(self):
        super(WithUserAndBugsApp, self).setUp()
        c.user = User(username='test-user')
        h.set_context('test', 'bugs')


class TestWhenSearchingWithCustomFields(WithUserAndBugsApp):
    def setUp(self):
        super(TestWhenSearchingWithCustomFields, self).setUp()
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
    def setUp(self):
        super(TestWhenLoadingFrontPage, self).setUp()
        with mongo_search_returning_colors_are_wrong_ticket():
            self.response = tracker_main.RootController().index()

    def test_that_recent_tickets_are_shown(self):
        tickets = self.response['tickets']
        assert tickets[0].summary == 'colors are wrong'


def solr_search_returning_colors_are_wrong_ticket():
    ticket = create_colors_are_wrong_ticket()
    search_artifact = Mock()
    matches = Mock()
    matches.docs = [dict(ticket_num_i=ticket.ticket_num)]
    search_artifact.return_value = matches
    return patch('forgetracker.tracker_main.search_artifact', search_artifact)

def mongo_search_returning_colors_are_wrong_ticket():
    ticket = create_colors_are_wrong_ticket()
    tickets = [ ticket ]
    paged_query = Mock()
    paged_query.return_value = dict(tickets=tickets)
    return patch('forgetracker.tracker_main.TM.Ticket.paged_query', paged_query)


def create_colors_are_wrong_ticket():
    set_tracker_custom_fields([dict(name='_iteration_number',
                                    label='Iteration Number',
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

