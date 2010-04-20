from mock import Mock
from pylons import c
from pyforge.lib import helpers as h
from ming.orm.ormsession import ThreadLocalORMSession

from forgetracker.model import Ticket, Globals
from forgetracker.tests.unit import TestWithModel


class TestTicketModel(TestWithModel):
    def test_that_it_has_ordered_custom_fields(self):
        custom_fields = dict(my_field='my value')
        Ticket(summary='my ticket', custom_fields=custom_fields)
        ThreadLocalORMSession.flush_all()
        ticket = Ticket.query.get(summary='my ticket')
        assert ticket.custom_fields == dict(my_field='my value')

