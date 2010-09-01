from mock import patch
from ming.orm.ormsession import ThreadLocalORMSession

from pylons import c

from forgetracker.tests.unit import TrackerTestWithModel
from forgetracker.widgets import ticket_form
from forgetracker.model import Globals


class TestTicketForm(TrackerTestWithModel):
    def test_it_creates_status_field(self):
        g = c.app.globals
        g.open_status_names = 'open'
        g.closed_status_names = 'closed'
        ThreadLocalORMSession.flush_all()
        assert self.options_for_field('status') == ['open', 'closed']

    @patch('ew.Option')
    def test_it_creates_milestone_field(self, option_class):
        c.app.globals.milestone_names = 'release1 release2'
        ThreadLocalORMSession.flush_all()
        none_option = option_class()
        assert self.options_for_field('milestone') == [none_option, 'release1', 'release2']

    def options_for_field(self, field_name):
        fields = ticket_form.TicketForm().fields
        matching_fields = [field
                           for field in fields
                           if field.name == field_name]
        return matching_fields[0].options

