#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import forms as f


class MilestonesAdmin(ffw.SortableTable):
    defaults = dict(
        ffw.SortableTable.defaults,
        button=ffw.AdminField(field=ew.InputField(
            css_class='add', field_type='button',
            value='New Milestone')),
        empty_msg='No milestones have been created.',
        nonempty_msg='Drag and drop the milestones to reorder.',
        repetitions=0)
    fields = [
        ew.HiddenField(name='old_name'),
        ffw.Radio(name='default', label='Default',
                  css_class='default-milestone'),
        ew.Checkbox(name='complete', show_label=True, suppress_label=True),
        ew.TextField(name='name',
                     attrs={'style': 'width: 80px'}),
        ffw.DateField(name='due_date',
                      attrs={'style': 'width: 80px'}),
        ffw.AutoResizeTextarea(
            name='description',
            attrs={'style': 'height:1em; width: 150px'}),
        ew.InputField(
            label='Delete',
            field_type='button',
            attrs={'class': 'delete', 'value': 'Delete'}),
    ]
    button = ew.InputField(
        css_class='add', field_type='button', value='New Milestone')

    def prepare_context(self, context):
        response = super().prepare_context(context)
        if 'value' in response:
            for milestone_data in response['value']:
                if 'name' in milestone_data:
                    milestone_data['old_name'] = milestone_data['name']
        return response

    def resources(self):
        yield from super().resources()
        yield ew.CSSScript('''div.state-field table{ width: 700px; }''')


class CustomFieldAdminDetail(ffw.StateField):
    template = 'jinja:forgetracker:templates/tracker_widgets/custom_field_admin_detail.html'
    defaults = dict(
        ffw.StateField.defaults,
        selector=ffw.AdminField(field=ew.SingleSelectField(
            name='type',
            options=[
                ew.Option(py_value='string', label='Text'),
                ew.Option(py_value='number', label='Number'),
                ew.Option(py_value='boolean', label='Boolean'),
                ew.Option(py_value='select', label='Select'),
                ew.Option(py_value='milestone', label='Milestone'),
                ew.Option(py_value='user', label='User'),
            ],
        )),
        states=dict(
            select=ffw.FieldCluster(
                fields=[
                    ffw.AdminField(field=ew.TextField(name='options',
                                                      label='Options (separate with spaces; quote if containing spaces; prefix with * to set a default)',
                                                      ))],
                show_labels=False),
            milestone=ffw.FieldCluster(
                # name='milestones',
                fields=[MilestonesAdmin(name='milestones')])
        ))


class CustomFieldAdmin(ew.CompoundField):
    template = 'jinja:forgetracker:templates/tracker_widgets/custom_field_admin.html'

    def resources(self):
        yield from super().resources()
        yield ew.JSLink('tracker_js/custom-fields.js')

    fields = [
        ew.HiddenField(name='name'),
        ew.TextField(name='label'),
        ew.Checkbox(
            name='show_in_search',
            label='Show in list view',
            show_label=True,
            suppress_label=True),
        CustomFieldAdminDetail()]


class TrackerFieldAdmin(f.ForgeForm):
    submit_text = None

    class fields(ew_core.NameList):
        open_status_names = ew.TextField(label='Open Statuses')
        closed_status_names = ew.TextField(label='Closed Statuses')
        custom_fields = ffw.SortableRepeatedField(field=CustomFieldAdmin())

    class buttons(ew_core.NameList):
        save = ew.SubmitButton(label='Save')
        cancel = ew.SubmitButton(
            label="Cancel",
            css_class='cancel', attrs=dict(
                onclick='window.location.reload(); return false;'))

    def resources(self):
        yield from self.fields['custom_fields'].resources()


class CustomFieldDisplay(ew.CompoundField):
    template = 'jinja:forgetracker:templates/tracker_widgets/custom_field_display.html'


class CustomFieldsDisplay(ew.RepeatedField):
    template = 'jinja:forgetracker:templates/tracker_widgets/custom_fields_display.html'


class TrackerFieldDisplay(f.ForgeForm):

    class fields(ew_core.NameList):
        milestone_names = ew.TextField()
        open_status_names = ew.TextField(label='Open Statuses')
        closed_status_names = ew.TextField(label='Open Statuses')
        custom_fields = CustomFieldsDisplay()

    def resources(self):
        yield from self.fields['custom_fields'].resources()
