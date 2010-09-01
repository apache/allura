import ew
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import forms as f

from pylons import c
from forgetracker import model
from formencode import validators as fev

class CustomFieldAdmin(ew.CompoundField):
    template='genshi:forgetracker.widgets.templates.custom_field_admin'

    def resources(self):
        yield ew.JSLink('tool/Tickets/js/custom-fields.js')

    class fields(ew.WidgetsList):
        label = ew.TextField()
        type = ew.SingleSelectField(
            show_label=False,
            options=[
                ew.Option(py_value='string', label='text'),
                ew.Option(py_value='number', label='number'),
                ew.Option(py_value='boolean', label='boolean'),
                ew.Option(py_value='select', label='select') ],
            )
        options = ew.TextField()
        show_in_search = ew.Checkbox(label='Show in search', suppress_label=True)

class CustomFieldDisplay(ew.CompoundField):
    template='genshi:forgetracker.widgets.templates.custom_field_display'
    class fields(ew.WidgetsList):
        label = ew.TextField()
        type = ew.SingleSelectField(
            show_label=False,
            options=[
                ew.Option(py_value='string', label='text'),
                ew.Option(py_value='number', label='number'),
                ew.Option(py_value='boolean', label='boolean'),
                ew.Option(py_value='select', label='select') ],
            )
        options = ew.TextField()
        show_in_search = ew.Checkbox(label='Show in search')

class CustomFieldsAdmin(ew.RepeatedField):
    template='genshi:forgetracker.widgets.templates.custom_fields_admin'
    params=['field']
    field=CustomFieldAdmin()

    def resources(self):
        for rr in self.field.resources():
            yield rr

class CustomFieldsDisplay(ew.RepeatedField):
    template='genshi:forgetracker.widgets.templates.custom_fields_display'
    params=['field_widget']
    field_widget=CustomFieldAdmin()

    def resources(self):
        for rr in self.field_widget.resources():
            yield rr

class TrackerFieldAdmin(f.ForgeForm):
    submit_text=None
    class fields(ew.WidgetsList):
        milestone_names = ew.TextField()
        open_status_names = ew.TextField(label='Open Statuses')
        closed_status_names = ew.TextField(label='Open Statuses')
        custom_fields = CustomFieldsAdmin()

    class buttons(ew.WidgetsList):
        add =  ew.SubmitButton(attrs={'class':'add', 'type':'button'})
        save = ew.SubmitButton()

    def resources(self):
        for rr in self.fields['custom_fields'].resources():
            yield rr

class TrackerFieldDisplay(f.ForgeForm):
    template='genshi:forgetracker.widgets.templates.tracker_field_display'
    class fields(ew.WidgetsList):
        milestone_names = ew.TextField()
        open_status_names = ew.TextField(label='Open Statuses')
        closed_status_names = ew.TextField(label='Open Statuses')
        custom_fields = CustomFieldsDisplay()
    def resources(self):
        for rr in self.fields['custom_fields'].resources():
            yield rr
