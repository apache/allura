import ew.jinja2_ew as ew

from formencode import validators as fev
from allura.lib.widgets import forms as ff
from allura.lib.widgets import form_fields as ffw

class OptionsAdmin(ff.AdminForm):
    template='jinja:forgetracker:templates/tracker_widgets/options_admin.html'
    defaults=dict(
        ff.ForgeForm.defaults,
        submit_text = 'Save')

    @property
    def fields(self):
        fields = [
            ew.TextField(
                name='TicketMonitoringEmail',
                label='Email ticket notifications to',
                validator=fev.Email(),
                grid_width='7'),
            ew.SingleSelectField(
                name='TicketMonitoringType',
                label='Send notifications for',
                grid_width='7',
                options=[
                    ew.Option(py_value='NewTicketsOnly', label='New tickets only'),
                    ew.Option(py_value='AllTicketChanges', label='All ticket changes')]),
            ffw.MarkdownEdit(
                name='TicketHelpNew',
                label='Help text to display on new ticket page',
                validator=fev.String(),
                attrs={'style': 'width: 95%'}),
            ffw.MarkdownEdit(
                name='TicketHelpSearch',
                label='Help text to display on ticket list pages (index page,'
                      ' search results, milestone lists)',
                validator=fev.String(),
                attrs={'style': 'width: 95%'}),
        ]
        return fields
