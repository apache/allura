from forgetracker.model import Globals
from forgetracker.tests.unit import TestWithModel
from pylons import c
from pyforge.lib import helpers as h

from ming.orm.ormsession import ThreadLocalORMSession


class TestGlobalsModel(TestWithModel):
    def setUp(self):
        super(TestGlobalsModel, self).setUp()
        c.project.install_app('Tickets', 'doc-bugs')
        ThreadLocalORMSession.flush_all()

    def test_it_has_current_tracker_globals(self):
        bugs_globals = Globals.query.get(app_config_id=c.app.config._id)
        assert Globals.for_current_tracker() == bugs_globals
        h.set_context('test', 'doc-bugs')
        assert Globals.for_current_tracker() != bugs_globals

    def test_next_ticket_number_increments(self):
        assert Globals.next_ticket_num() == 1
        assert Globals.next_ticket_num() == 2

    def test_ticket_numbers_are_independent(self):
        assert Globals.next_ticket_num() == 1
        h.set_context('test', 'doc-bugs')
        assert Globals.next_ticket_num() == 1


class TestCustomFields(TestWithModel):
    def test_it_has_sortable_custom_fields(self):
        tracker_globals = globals_with_custom_fields(
            [dict(label='Iteration Number',
                  name='_iteration_number',
                  show_in_search=False),
             dict(label='Point Estimate',
                  name='_point_estimate',
                  show_in_search=True)])
        expected = [dict(sortable_name='_point_estimate_s',
                         name='_point_estimate',
                         label='Point Estimate')]
        assert tracker_globals.sortable_custom_fields_shown_in_search() == expected


def globals_with_custom_fields(custom_fields):
    tracker_globals = Globals.for_current_tracker()
    tracker_globals.custom_fields = custom_fields
    ThreadLocalORMSession.flush_all()
    tracker_globals = Globals.for_current_tracker()
    return tracker_globals

