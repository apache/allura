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

from __future__ import unicode_literals
from __future__ import absolute_import
import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import forms
import six



class TicketSearchResults(ew_core.SimpleForm):
    template = 'jinja:forgetracker:templates/tracker_widgets/ticket_search_results.html'
    defaults = dict(
        ew_core.SimpleForm.defaults,
        solr_error=None,
        count=None,
        limit=None,
        query=None,
        tickets=None,
        sortable_custom_fields=None,
        page=1,
        sort=None,
        columns=None)

    class fields(ew_core.NameList):
        page_list = ffw.PageList()
        page_size = ffw.PageSize()
        lightbox = ffw.Lightbox(name='col_list', trigger='#col_menu')

    def __init__(self, filters, *args, **kw):
        super(TicketSearchResults, self).__init__(*args, **kw)
        self.filters = {}
        for name, field in six.iteritems(filters):
            self.filters[name] = options = [{
                'value': val,
                'label': '%s (%s)' % (val, count),
                'selected': False
            } for val, count in field]
            options.append({'value': '', 'label': 'Not set', 'selected': False})

    def resources(self):
        yield ew.JSLink('allura/js/jquery-ui.min.js', location='body_top_js')
        yield ew.JSLink('tracker_js/jquery.multiselect.min.js')
        yield ew.CSSLink('allura/css/smoothness/jquery-ui.min.css')
        yield ew.CSSLink('tracker_css/jquery.multiselect.css')
        yield ew.JSLink('tracker_js/ticket-list.js')
        yield ew.CSSLink('tracker_css/ticket-list.css')
        for r in super(TicketSearchResults, self).resources():
            yield r


class MassEdit(ew_core.SimpleForm):
    template = 'jinja:forgetracker:templates/tracker_widgets/mass_edit.html'
    defaults = dict(
        ew_core.SimpleForm.defaults,
        count=None,
        limit=None,
        query=None,
        tickets=None,
        page=1,
        sort=None)

    class fields(ew_core.NameList):
        page_list = ffw.PageList()
        page_size = ffw.PageSize()
        lightbox = ffw.Lightbox(name='col_list', trigger='#col_menu')

    def resources(self):
        yield ew.CSSLink('tracker_css/ticket-list.css')
        for r in super(MassEdit, self).resources():
            yield r


class MassEditForm(ew_core.Widget):
    template = 'jinja:forgetracker:templates/tracker_widgets/mass_edit_form.html'
    defaults = dict(
        ew_core.Widget.defaults,
        globals=None,
        query=None,
        cancel_href=None,
        limit=None,
        sort=None)

    def resources(self):
        yield ew.JSLink('tracker_js/mass-edit.js')


class MassMoveForm(forms.MoveTicketForm):
    defaults = dict(
        forms.MoveTicketForm.defaults,
        action='.')

    def resources(self):
        yield ew.JSLink('tracker_js/mass-edit.js')
