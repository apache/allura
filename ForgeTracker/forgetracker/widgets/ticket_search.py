import tg

from pylons import c

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets import form_fields as ffw

class TicketSearchResults(ew_core.SimpleForm):
    template='jinja:forgetracker:templates/tracker_widgets/ticket_search_results.html'
    defaults=dict(
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
        page_list=ffw.PageList()
        page_size=ffw.PageSize()
        lightbox=ffw.Lightbox(name='col_list',trigger='#col_menu')

    def resources(self):
        yield ew.JSLink('tracker_js/ticket-list.js')
        yield ew.CSSLink('tracker_css/ticket-list.css')
        for r in super(TicketSearchResults, self).resources():
            yield r

class MassEdit(ew_core.Widget):
    template='jinja:forgetracker:templates/tracker_widgets/mass_edit.html'
    defaults=dict(
        ew_core.Widget.defaults,
        count=None,
        limit=None,
        query=None,
        tickets=None,
        page=1,
        sort=None)

    def resources(self):
        yield ew.JSLink('tracker_js/ticket-list.js')

class MassEditForm(ew_core.Widget):
    template='jinja:forgetracker:templates/tracker_widgets/mass_edit_form.html'
    defaults=dict(
        ew_core.Widget.defaults,
        globals=None,
        query=None,
        cancel_href=None,
        limit=None,
        sort=None)

    def resources(self):
        yield ew.JSLink('tracker_js/mass-edit.js')
