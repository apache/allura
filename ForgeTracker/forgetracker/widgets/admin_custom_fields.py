import ew
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import forms as f

from pylons import c
from forgetracker import model
from formencode import validators as fev

class MilestonesAdmin(ffw.SortableTable):
    button=ffw.AdminField(field=ew.InputField(
            css_class='add', field_type='button',
            value='New Milestone'))
    empty_msg='No milestones have been created.'
    nonempty_msg='Drag and drop the milestones to reorder.'
    repetitions=0
    fields = [
        ew.Checkbox(name='complete', show_label=True, suppress_label=True),
        ew.TextField(name='name'),
        ffw.DateField(name='due_date'),
        ew.InputField(
            label='Delete',
            field_type='button',
            attrs={'class':'delete', 'value':'Delete Milestone'}) ]

class CustomFieldAdminDetail(ffw.StateField):
    template='genshi:forgetracker.widgets.templates.custom_field_admin_detail'
    selector=ffw.AdminField(field=ew.SingleSelectField(
            name='type',
            options=[
                ew.Option(py_value='string', label='Text'),
                ew.Option(py_value='number', label='Number'),
                ew.Option(py_value='boolean', label='Boolean'),
                ew.Option(py_value='select', label='Select'),
                ew.Option(py_value='milestone', label='Milestone'),
                ],
            ))
    states=dict(
        select=ffw.FieldCluster(
            fields=[
                ffw.AdminField(field=ew.TextField(name='options')) ],
            show_labels=False),
        milestone=ffw.FieldCluster(
            # name='milestones',
            fields=[ MilestonesAdmin(name='milestones') ])
        )

class CustomFieldAdmin(ew.CompoundField):
    template='genshi:forgetracker.widgets.templates.custom_field_admin'

    def resources(self):
        for r in super(CustomFieldAdmin, self).resources():
            yield r
        yield ew.JSLink('tool/Tickets/js/custom-fields.js')

    fields = [
        ew.TextField(name='label'),
        ew.Checkbox(
            name='show_in_search',
            label='Show in search',
            show_label=True,
            suppress_label=True),
        CustomFieldAdminDetail() ]

class TrackerFieldAdmin(f.ForgeForm):
    submit_text=None
    class fields(ew.WidgetsList):
        open_status_names = ew.TextField(label='Open Statuses')
        closed_status_names = ew.TextField(label='Open Statuses')
        custom_fields = ffw.SortableRepeatedField(field=CustomFieldAdmin())
    class buttons(ew.WidgetsList):
        save = ew.SubmitButton()
        cancel = ew.SubmitButton(
            css_class='cancel', attrs=dict(
                onclick='window.location.reload(); return false;'))

    def resources(self):
        for rr in self.fields['custom_fields'].resources():
            yield rr

class CustomFieldDisplay(ew.CompoundField):
    template='genshi:forgetracker.widgets.templates.custom_field_display'
    pass

class CustomFieldsDisplay(ew.RepeatedField):
    template='genshi:forgetracker.widgets.templates.custom_fields_display'
    pass

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
