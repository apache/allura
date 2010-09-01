from ming.orm.ormsession import ThreadLocalORMSession

from pylons import c

from forgetracker.tests.unit import TrackerTestWithModel
from forgetracker.widgets import ticket_form
from forgetracker.model import Globals


class TestTicketCustomFields(TrackerTestWithModel):
    def test_it_creates_string_fields(self):
        globals_ = c.app.globals
        globals_.custom_fields = [dict(name='_iteration_number',
                                       label='Iteration Number',
                                       type='string')]
        ThreadLocalORMSession.flush_all()
        fields = ticket_form.TicketCustomFields().fields
        iteration_field = fields[0]
        assert iteration_field.label == 'Iteration Number'
        assert iteration_field.name == '_iteration_number'

