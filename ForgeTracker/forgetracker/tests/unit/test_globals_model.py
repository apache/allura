from forgetracker.model import Globals
from forgetracker.tests.unit import TestWithModel
from pylons import c
from pyforge.lib import helpers as h

from ming.orm.ormsession import ThreadLocalORMSession


class TestGlobalsModel(TestWithModel):
    def test_it_has_current_tracker_globals(self):
        bugs_globals = Globals.query.get(app_config_id=c.app.config._id)
        assert Globals.for_current_tracker() == bugs_globals
        c.project.install_app('Tickets', 'doc_bugs')
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'doc_bugs')
        assert Globals.for_current_tracker() != bugs_globals

    def test_next_ticket_number_increments(self):
        assert Globals.next_ticket_num() == 1
        assert Globals.next_ticket_num() == 2

    def test_ticket_numbers_are_independent(self):
        assert Globals.next_ticket_num() == 1
        c.project.install_app('Tickets', 'doc_bugs')
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'doc_bugs')
        assert Globals.next_ticket_num() == 1

