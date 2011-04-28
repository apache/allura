from ming.orm.ormsession import ThreadLocalORMSession
from ming import schema
from nose.tools import raises, assert_raises

from forgetracker.model import Ticket
from forgetracker.tests.unit import TrackerTestWithModel


class TestTicketModel(TrackerTestWithModel):
    def test_that_it_has_ordered_custom_fields(self):
        custom_fields = dict(my_field='my value')
        Ticket(summary='my ticket', custom_fields=custom_fields, ticket_num=3)
        ThreadLocalORMSession.flush_all()
        ticket = Ticket.query.get(summary='my ticket')
        assert ticket.custom_fields == dict(my_field='my value')

    @raises(schema.Invalid)
    def test_ticket_num_required(self):
        Ticket(summary='my ticket')

    def test_ticket_num_required2(self):
        t = Ticket(summary='my ticket', ticket_num=3)
        try:
            t.ticket_num = None
        except schema.Invalid:
            pass
        else:
            raise AssertionError('Expected schema.Invalid to be thrown')
