import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import forms as f

from pylons import c
from forgetracker import model
from formencode import validators as fev

class MilestonesAdmin(ffw.SortableTable):
    defaults=dict(
        ffw.SortableTable.defaults,
        button=ffw.AdminField(field=ew.InputField(
                css_class='add', field_type='button',
                value='New Milestone')),
        empty_msg='No milestones have been created.',
        nonempty_msg='Drag and drop the milestones to reorder.',
        repetitions=0)
    fields = [
        ew.Checkbox(name='complete', show_label=True, suppress_label=True),
        ew.TextField(name='name'),
        ffw.DateField(name='due_date'),
        ffw.AutoResizeTextarea(
            name='description',
            attrs={'style':'height:2em; width: 300px'}),
        ew.InputField(
            label='Delete',
            field_type='button',
            attrs={'class':'delete', 'value':'Delete Milestone'}),
        ]

class CustomFieldAdminDetail(ffw.StateField):
    template='jinja:tracker_widgets/custom_field_admin_detail.html'
    defaults=dict(
        ffw.StateField.defaults,
        selector=ffw.AdminField(field=ew.SingleSelectField(
                name='type',
                options=[
                    ew.Option(py_value='string', label='Text'),
                    ew.Option(py_value='number', label='Number'),
                    ew.Option(py_value='boolean', label='Boolean'),
                    ew.Option(py_value='select', label='Select'),
                    ew.Option(py_value='milestone', label='Milestone'),
                    ],
                )),
        states=dict(
            select=ffw.FieldCluster(
                fields=[
                    ffw.AdminField(field=ew.TextField(name='options')) ],
                show_labels=False),
            milestone=ffw.FieldCluster(
                # name='milestones',
                fields=[ MilestonesAdmin(name='milestones') ])
            ))

class CustomFieldAdmin(ew.CompoundField):
    template='jinja:tracker_widgets/custom_field_admin.html'

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
    class fields(ew_core.NameList):
        open_status_names = ew.TextField(label='Open Statuses')
        closed_status_names = ew.TextField(label='Closed Statuses')
        custom_fields = ffw.SortableRepeatedField(field=CustomFieldAdmin())
    class buttons(ew_core.NameList):
        save = ew.SubmitButton()
        cancel = ew.SubmitButton(
            css_class='cancel', attrs=dict(
                onclick='window.location.reload(); return false;'))

    def resources(self):
        for rr in self.fields['custom_fields'].resources():
            yield rr

class CustomFieldDisplay(ew.CompoundField):
    template='jinja:tracker_widgets/custom_field_display.html'

class CustomFieldsDisplay(ew.RepeatedField):
    template='jinja:tracker_widgets/custom_fields_display.html'

class TrackerFieldDisplay(f.ForgeForm):
    class fields(ew_core.NameList):
        milestone_names = ew.TextField()
        open_status_names = ew.TextField(label='Open Statuses')
        closed_status_names = ew.TextField(label='Open Statuses')
        custom_fields = CustomFieldsDisplay()
    def resources(self):
        for rr in self.fields['custom_fields'].resources():
            yield rr
