import ew.jinja2_ew as ew

from formencode import validators as fev
from allura.lib.widgets import forms as ff

class OptionsAdmin(ff.AdminForm):
    defaults=dict(
        ff.ForgeForm.defaults,
        submit_text = 'Save')

    @property
    def fields(self):
        fields = [
            ew.TextField(
                name='TicketMonitoringEmail',
                label='Email ticket notifications to',
                validator=fev.Email()),
            ew.SingleSelectField(
                name='TicketMonitoringType',
                label='Send notifications for',
                options=[
                    ew.Option(py_value='NewTicketsOnly', label='New tickets only'),
                    ew.Option(py_value='AllTicketChanges', label='All ticket changes')])
        ]
        return fields
