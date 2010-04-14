from mock import Mock
from pylons import c
from pyforge.lib import helpers as h
from ming.orm.ormsession import ThreadLocalORMSession

from forgetracker.model import Ticket, Globals
from forgetracker.tests.unit import TestWithModel


class TestTicketModel(TestWithModel):
    def test_that_it_has_ordered_custom_fields(self):
        field_names = field_values = not_sorted(['field1', 'field2'])
        custom_fields = dict(zip(field_names, field_values))
        ticket = Ticket(custom_fields=custom_fields)

        set_current_tracker_field_names(field_names)
        assert ticket.ordered_custom_field_values == field_values


def set_current_tracker_field_names(field_names):
    tracker_globals = Globals.for_current_tracker()
    tracker_globals.custom_fields = [dict(name=name) for name in field_names]


def not_sorted(collection):
    """Return the collection in any order that's not sorted"""
    return list(reversed(sorted(collection)))

